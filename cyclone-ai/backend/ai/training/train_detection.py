"""Train and evaluate the event-split ResNet cyclone detection baseline.

Usage:
    python -m ai.training.train_detection --manifest data/cyclone_detection/manifest.csv
"""
from __future__ import annotations

import argparse
import json
import platform
import random
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ai.detection.config import CLASS_TO_INDEX, DetectionConfig
from ai.detection.dataset import load_manifest, records_for_split, validate_records
from ai.detection.model import build_model
from ai.detection.preprocessing import load_image_tensor


def _torch() -> Any:
    try:
        import torch
        from torch.utils.data import DataLoader, Dataset, WeightedRandomSampler
    except ImportError as exc:
        raise RuntimeError("Training requires torch and torchvision. Install backend/requirements.txt.") from exc
    return torch, DataLoader, Dataset, WeightedRandomSampler


def set_seed(seed: int) -> None:
    torch, _, _, _ = _torch()
    random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def select_device(requested: str) -> Any:
    torch, _, _, _ = _torch()
    if requested == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA was requested but is not available")
    return torch.device("cuda" if requested == "auto" and torch.cuda.is_available() else requested if requested != "auto" else "cpu")


def _metrics(labels: list[int], predictions: list[int], probabilities: list[float]) -> dict[str, Any]:
    total = len(labels)
    tp = sum(1 for label, prediction in zip(labels, predictions) if label == 1 and prediction == 1)
    tn = sum(1 for label, prediction in zip(labels, predictions) if label == 0 and prediction == 0)
    fp = sum(1 for label, prediction in zip(labels, predictions) if label == 0 and prediction == 1)
    fn = sum(1 for label, prediction in zip(labels, predictions) if label == 1 and prediction == 0)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "accuracy": (tp + tn) / total if total else 0.0,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "confusion_matrix": {"true_negative": tn, "false_positive": fp, "false_negative": fn, "true_positive": tp},
        "roc_auc": _binary_roc_auc(labels, probabilities),
    }


def _binary_roc_auc(labels: list[int], probabilities: list[float]) -> float | None:
    positives = sum(labels)
    negatives = len(labels) - positives
    if positives == 0 or negatives == 0:
        return None
    ranked = sorted(enumerate(probabilities), key=lambda item: item[1])
    rank_sum = sum(rank for rank, (index, _) in enumerate(ranked, start=1) if labels[index] == 1)
    return (rank_sum - positives * (positives + 1) / 2) / (positives * negatives)


def _evaluate(model: Any, loader: Any, criterion: Any, device: Any) -> tuple[float, dict[str, Any]]:
    torch, _, _, _ = _torch()
    model.eval()
    total_loss = 0.0
    labels: list[int] = []
    predictions: list[int] = []
    probabilities: list[float] = []
    with torch.inference_mode():
        for images, targets in loader:
            images, targets = images.to(device), targets.to(device)
            outputs = model(images)
            total_loss += float(criterion(outputs, targets).item()) * len(targets)
            scores = torch.softmax(outputs, dim=1)[:, 1]
            labels.extend(targets.cpu().tolist())
            predictions.extend((scores >= 0.5).long().cpu().tolist())
            probabilities.extend(scores.cpu().tolist())
    return total_loss / max(1, len(labels)), _metrics(labels, predictions, probabilities)


def train(config: DetectionConfig, *, manifest_path: Path, output_dir: Path, device_name: str) -> dict[str, Any]:
    torch, DataLoader, Dataset, WeightedRandomSampler = _torch()
    set_seed(config.seed)
    device = select_device(device_name)
    records = load_manifest(manifest_path)
    dataset_report = validate_records(records, check_images=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    class ManifestDataset(Dataset):
        def __init__(self, split: str, training: bool) -> None:
            self.records = records_for_split(records, split)
            self.training = training

        def __len__(self) -> int:
            return len(self.records)

        def __getitem__(self, index: int) -> tuple[Any, int]:
            record = self.records[index]
            return (
                load_image_tensor(record.image_path, image_size=config.image_size, training=self.training),
                CLASS_TO_INDEX[record.label],
            )

    train_data = ManifestDataset("train", training=True)
    val_data = ManifestDataset("val", training=False)
    test_data = ManifestDataset("test", training=False)
    train_labels = [CLASS_TO_INDEX[record.label] for record in train_data.records]
    counts = Counter(train_labels)
    imbalance_ratio = max(counts.values()) / min(counts.values())
    sampler = None
    if imbalance_ratio >= 1.5:
        sampler = WeightedRandomSampler(
            [1.0 / counts[label] for label in train_labels], len(train_labels), replacement=True
        )
    train_loader = DataLoader(
        train_data, batch_size=config.batch_size, sampler=sampler,
        shuffle=sampler is None, num_workers=0,
    )
    val_loader = DataLoader(val_data, batch_size=config.batch_size, shuffle=False, num_workers=0)
    test_loader = DataLoader(test_data, batch_size=config.batch_size, shuffle=False, num_workers=0)

    model = build_model(config, use_pretrained_weights=config.pretrained).to(device)
    criterion = torch.nn.CrossEntropyLoss()
    optimizer = torch.optim.AdamW(model.parameters(), lr=config.learning_rate, weight_decay=config.weight_decay)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, mode="min", patience=2, factor=0.5)
    use_amp = device.type == "cuda"
    scaler = torch.amp.GradScaler("cuda", enabled=use_amp)
    history: list[dict[str, Any]] = []
    best_val_loss = float("inf")
    best_validation_metrics: dict[str, Any] | None = None
    stale_epochs = 0
    model_version = f"detection-{config.model_name}-v1"
    started = time.monotonic()

    for epoch in range(1, config.epochs + 1):
        model.train()
        running_loss = 0.0
        train_labels_epoch: list[int] = []
        train_predictions: list[int] = []
        train_probabilities: list[float] = []
        for images, targets in train_loader:
            images, targets = images.to(device), targets.to(device)
            optimizer.zero_grad(set_to_none=True)
            with torch.autocast(device_type=device.type, enabled=use_amp):
                outputs = model(images)
                loss = criterion(outputs, targets)
            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()
            running_loss += float(loss.item()) * len(targets)
            scores = torch.softmax(outputs.detach(), dim=1)[:, 1]
            train_labels_epoch.extend(targets.cpu().tolist())
            train_predictions.extend((scores >= 0.5).long().cpu().tolist())
            train_probabilities.extend(scores.cpu().tolist())

        train_loss = running_loss / max(1, len(train_data))
        val_loss, val_metrics = _evaluate(model, val_loader, criterion, device)
        scheduler.step(val_loss)
        history.append({
            "epoch": epoch,
            "train_loss": train_loss,
            "validation_loss": val_loss,
            "train_metrics": _metrics(train_labels_epoch, train_predictions, train_probabilities),
            "validation_metrics": val_metrics,
            "learning_rate": optimizer.param_groups[0]["lr"],
        })
        checkpoint = {
            "state_dict": model.state_dict(), "config": config.to_dict(), "model_version": model_version,
            "dataset_report": dataset_report, "trained_at_utc": datetime.now(timezone.utc).isoformat(),
        }
        torch.save(checkpoint, output_dir / "last.pt")
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_validation_metrics = val_metrics
            stale_epochs = 0
            torch.save(checkpoint, output_dir / "best.pt")
        else:
            stale_epochs += 1
            if stale_epochs >= config.patience:
                break

    best_checkpoint = torch.load(output_dir / "best.pt", map_location=device, weights_only=False)
    model.load_state_dict(best_checkpoint["state_dict"])
    test_loss, test_metrics = _evaluate(model, test_loader, criterion, device)
    environment = {
        "python": platform.python_version(), "torch": torch.__version__,
        "cuda_available": torch.cuda.is_available(), "cuda_version": torch.version.cuda,
        "device": str(device),
    }
    result = {
        "model_version": model_version, "dataset_version": config.dataset_version,
        "architecture": config.model_name, "config": config.to_dict(), "dataset": dataset_report,
        "class_imbalance_strategy": "weighted_sampler" if sampler else "none (classes are balanced)",
        "environment": environment, "training_duration_seconds": round(time.monotonic() - started, 2),
        "best_validation": best_validation_metrics, "best_validation_loss": best_val_loss,
        "test_loss": test_loss, "test_metrics": test_metrics,
        "evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    (output_dir / "config.json").write_text(json.dumps(config.to_dict(), indent=2), encoding="utf-8")
    (output_dir / "training_history.json").write_text(json.dumps(history, indent=2), encoding="utf-8")
    (output_dir / "evaluation.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Train CycloneAI's event-split ResNet detector")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("../models/detection"))
    parser.add_argument("--model", choices=("resnet18", "resnet50"), default="resnet18")
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--learning-rate", type=float, default=1e-4)
    parser.add_argument("--image-size", type=int, default=224)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--dataset-version", default="unconfigured")
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument("--no-pretrained", action="store_true")
    args = parser.parse_args()
    config = DetectionConfig(
        model_name=args.model, image_size=args.image_size, batch_size=args.batch_size,
        epochs=args.epochs, learning_rate=args.learning_rate, seed=args.seed,
        dataset_version=args.dataset_version, pretrained=not args.no_pretrained,
    )
    result = train(config, manifest_path=args.manifest, output_dir=args.output_dir, device_name=args.device)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
