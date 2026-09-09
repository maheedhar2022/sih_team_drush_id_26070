"""Train and evaluate a shared-backbone intensity classifier/regressor.

The manifest and its authoritative label mapping are validated before Torch is
imported, so event leakage and timestamp mismatch fail early.
"""
from __future__ import annotations

import argparse
import json
import math
import platform
import random
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, pstdev
from typing import Any

from ai.detection.preprocessing import load_image_tensor
from ai.intensity.config import IntensityConfig
from ai.intensity.dataset import load_label_mapping, load_manifest, records_for_split, validate_records
from ai.intensity.model import build_model


def _torch() -> Any:
    try:
        import torch
        from torch.utils.data import DataLoader, Dataset, WeightedRandomSampler
    except ImportError as exc:
        raise RuntimeError("Intensity training requires torch and torchvision. Install backend/requirements.txt.") from exc
    return torch, DataLoader, Dataset, WeightedRandomSampler


def _set_seed(seed: int) -> None:
    torch, _, _, _ = _torch()
    random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def _device(requested: str) -> Any:
    torch, _, _, _ = _torch()
    if requested == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA was requested but is unavailable")
    return torch.device("cuda" if requested == "auto" and torch.cuda.is_available() else requested if requested != "auto" else "cpu")


def _classification_metrics(labels: list[int], predictions: list[int], label_names: list[str]) -> dict[str, Any]:
    total = len(labels)
    per_class: dict[str, dict[str, float | int]] = {}
    f1_values: list[float] = []
    weighted_f1_sum = 0.0
    for index, label_name in enumerate(label_names):
        tp = sum(1 for actual, predicted in zip(labels, predictions) if actual == index and predicted == index)
        fp = sum(1 for actual, predicted in zip(labels, predictions) if actual != index and predicted == index)
        fn = sum(1 for actual, predicted in zip(labels, predictions) if actual == index and predicted != index)
        support = sum(1 for actual in labels if actual == index)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        per_class[label_name] = {"precision": precision, "recall": recall, "f1": f1, "support": support}
        f1_values.append(f1)
        weighted_f1_sum += f1 * support
    confusion = [[sum(1 for actual, predicted in zip(labels, predictions) if actual == row and predicted == column) for column in range(len(label_names))] for row in range(len(label_names))]
    return {
        "accuracy": sum(actual == predicted for actual, predicted in zip(labels, predictions)) / total if total else 0.0,
        "macro_precision": sum(float(metric["precision"]) for metric in per_class.values()) / len(label_names),
        "macro_recall": sum(float(metric["recall"]) for metric in per_class.values()) / len(label_names),
        "macro_f1": sum(f1_values) / len(f1_values), "weighted_f1": weighted_f1_sum / total if total else 0.0,
        "per_class": per_class, "confusion_matrix": {"labels": label_names, "matrix": confusion},
    }


def _regression_metrics(targets: list[float], predictions: list[float], unit: str) -> dict[str, float | str | None]:
    if not targets:
        return {"mae": None, "rmse": None, "r2": None, "unit": unit}
    mae = sum(abs(actual - predicted) for actual, predicted in zip(targets, predictions)) / len(targets)
    mse = sum((actual - predicted) ** 2 for actual, predicted in zip(targets, predictions)) / len(targets)
    target_mean = mean(targets)
    total_variance = sum((actual - target_mean) ** 2 for actual in targets)
    r2 = 1 - sum((actual - predicted) ** 2 for actual, predicted in zip(targets, predictions)) / total_variance if total_variance else None
    return {"mae": mae, "rmse": math.sqrt(mse), "r2": r2, "unit": unit}


def train(config: IntensityConfig, *, manifest_path: Path, label_mapping_path: Path, output_dir: Path, device_name: str) -> dict[str, Any]:
    label_mapping = load_label_mapping(label_mapping_path)
    records = load_manifest(manifest_path, label_mapping)
    dataset_report = validate_records(records, timestamp_tolerance_minutes=config.timestamp_tolerance_minutes)
    torch, DataLoader, Dataset, WeightedRandomSampler = _torch()
    _set_seed(config.seed)
    device = _device(device_name)
    labels = label_mapping["labels"]
    category_to_index = {label: index for index, label in enumerate(labels)}
    train_records = records_for_split(records, "train")
    wind_values = [record.wind_speed_kmh for record in train_records if record.wind_speed_kmh is not None]
    pressure_values = [record.central_pressure_hpa for record in train_records if record.central_pressure_hpa is not None]
    predict_wind, predict_pressure = bool(wind_values), bool(pressure_values)
    target_statistics = {
        "wind": {"mean": mean(wind_values), "std": max(pstdev(wind_values), 1e-6)} if predict_wind else None,
        "pressure": {"mean": mean(pressure_values), "std": max(pstdev(pressure_values), 1e-6)} if predict_pressure else None,
    }
    output_dir.mkdir(parents=True, exist_ok=True)

    class IntensityDataset(Dataset):
        def __init__(self, split: str, training: bool) -> None:
            self.records = records_for_split(records, split)
            self.training = training

        def __len__(self) -> int:
            return len(self.records)

        def __getitem__(self, index: int) -> tuple[Any, int, float, bool, float, bool]:
            record = self.records[index]
            wind = record.wind_speed_kmh
            pressure = record.central_pressure_hpa
            normalized_wind = (wind - target_statistics["wind"]["mean"]) / target_statistics["wind"]["std"] if wind is not None and predict_wind else 0.0
            normalized_pressure = (pressure - target_statistics["pressure"]["mean"]) / target_statistics["pressure"]["std"] if pressure is not None and predict_pressure else 0.0
            return (
                load_image_tensor(record.image_path, image_size=config.image_size, training=self.training),
                category_to_index[record.intensity_category], normalized_wind, wind is not None, normalized_pressure, pressure is not None,
            )

    train_data, val_data, test_data = IntensityDataset("train", True), IntensityDataset("val", False), IntensityDataset("test", False)
    class_counts = Counter(category_to_index[record.intensity_category] for record in train_records)
    imbalance_ratio = max(class_counts.values()) / min(class_counts.values())
    sampler = WeightedRandomSampler([1 / class_counts[category_to_index[record.intensity_category]] for record in train_records], len(train_records), replacement=True) if imbalance_ratio >= 1.5 else None
    train_loader = DataLoader(train_data, batch_size=config.batch_size, sampler=sampler, shuffle=sampler is None, num_workers=0)
    val_loader = DataLoader(val_data, batch_size=config.batch_size, shuffle=False, num_workers=0)
    test_loader = DataLoader(test_data, batch_size=config.batch_size, shuffle=False, num_workers=0)
    model = build_model(config, num_categories=len(labels), predict_wind=predict_wind, predict_pressure=predict_pressure, use_pretrained_weights=config.pretrained).to(device)
    category_loss = torch.nn.CrossEntropyLoss()
    regression_loss = torch.nn.SmoothL1Loss(reduction="none")
    optimizer = torch.optim.AdamW(model.parameters(), lr=config.learning_rate, weight_decay=config.weight_decay)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, mode="min", patience=2, factor=0.5)
    use_amp = device.type == "cuda"
    scaler = torch.amp.GradScaler("cuda", enabled=use_amp)

    def batch_loss(output: Any, categories: Any, wind: Any, wind_mask: Any, pressure: Any, pressure_mask: Any) -> Any:
        loss = category_loss(output["classification_logits"], categories)
        if predict_wind and wind_mask.any():
            loss = loss + config.wind_loss_weight * regression_loss(output["wind"][wind_mask], wind[wind_mask]).mean()
        if predict_pressure and pressure_mask.any():
            loss = loss + config.pressure_loss_weight * regression_loss(output["pressure"][pressure_mask], pressure[pressure_mask]).mean()
        return loss

    def evaluate(loader: Any) -> tuple[float, dict[str, Any]]:
        model.eval(); total_loss = 0.0; count = 0; actual_categories: list[int] = []; predicted_categories: list[int] = []
        actual_wind: list[float] = []; predicted_wind: list[float] = []; actual_pressure: list[float] = []; predicted_pressure: list[float] = []
        with torch.inference_mode():
            for images, categories, wind, wind_mask, pressure, pressure_mask in loader:
                images, categories = images.to(device), categories.to(device)
                wind, wind_mask = wind.to(device), wind_mask.to(device)
                pressure, pressure_mask = pressure.to(device), pressure_mask.to(device)
                output = model(images); loss = batch_loss(output, categories, wind, wind_mask, pressure, pressure_mask)
                total_loss += float(loss.item()) * len(categories); count += len(categories)
                actual_categories.extend(categories.cpu().tolist()); predicted_categories.extend(output["classification_logits"].argmax(dim=1).cpu().tolist())
                if predict_wind and wind_mask.any():
                    actual_wind.extend((wind[wind_mask] * target_statistics["wind"]["std"] + target_statistics["wind"]["mean"]).cpu().tolist())
                    predicted_wind.extend((output["wind"][wind_mask] * target_statistics["wind"]["std"] + target_statistics["wind"]["mean"]).cpu().tolist())
                if predict_pressure and pressure_mask.any():
                    actual_pressure.extend((pressure[pressure_mask] * target_statistics["pressure"]["std"] + target_statistics["pressure"]["mean"]).cpu().tolist())
                    predicted_pressure.extend((output["pressure"][pressure_mask] * target_statistics["pressure"]["std"] + target_statistics["pressure"]["mean"]).cpu().tolist())
        return total_loss / max(count, 1), {
            "classification": _classification_metrics(actual_categories, predicted_categories, labels),
            "wind_speed_kmh": _regression_metrics(actual_wind, predicted_wind, "km/h"),
            "central_pressure_hpa": _regression_metrics(actual_pressure, predicted_pressure, "hPa"),
        }

    history: list[dict[str, Any]] = []; best_loss = float("inf"); best_metrics: dict[str, Any] | None = None; stale_epochs = 0; started = time.monotonic()
    model_version = f"intensity-{config.backbone}-v1"
    for epoch in range(1, config.epochs + 1):
        model.train(); training_loss = 0.0; seen = 0
        for images, categories, wind, wind_mask, pressure, pressure_mask in train_loader:
            images, categories = images.to(device), categories.to(device); wind, wind_mask = wind.to(device), wind_mask.to(device); pressure, pressure_mask = pressure.to(device), pressure_mask.to(device)
            optimizer.zero_grad(set_to_none=True)
            with torch.autocast(device_type=device.type, enabled=use_amp):
                output = model(images); loss = batch_loss(output, categories, wind, wind_mask, pressure, pressure_mask)
            scaler.scale(loss).backward(); scaler.step(optimizer); scaler.update()
            training_loss += float(loss.item()) * len(categories); seen += len(categories)
        validation_loss, validation_metrics = evaluate(val_loader); scheduler.step(validation_loss)
        history.append({"epoch": epoch, "training_loss": training_loss / max(seen, 1), "validation_loss": validation_loss, "validation_metrics": validation_metrics, "learning_rate": optimizer.param_groups[0]["lr"]})
        checkpoint = {"state_dict": model.state_dict(), "config": config.to_dict(), "model_version": model_version, "label_mapping": label_mapping, "predict_wind": predict_wind, "predict_pressure": predict_pressure, "target_statistics": target_statistics, "dataset_report": dataset_report, "trained_at_utc": datetime.now(timezone.utc).isoformat()}
        torch.save(checkpoint, output_dir / "last.pt")
        if validation_loss < best_loss:
            best_loss, best_metrics, stale_epochs = validation_loss, validation_metrics, 0; torch.save(checkpoint, output_dir / "best.pt")
        else:
            stale_epochs += 1
            if stale_epochs >= config.patience: break
    best = torch.load(output_dir / "best.pt", map_location=device, weights_only=False); model.load_state_dict(best["state_dict"]); test_loss, test_metrics = evaluate(test_loader)
    report = {"model_version": model_version, "architecture": config.backbone, "config": config.to_dict(), "label_mapping": label_mapping, "dataset": dataset_report, "class_imbalance_strategy": "weighted_sampler" if sampler else "none (classes are balanced)", "target_statistics": target_statistics, "best_validation_loss": best_loss, "best_validation_metrics": best_metrics, "held_out_test": {"loss": test_loss, "metrics": test_metrics, "test_events": dataset_report["events_by_split"]["test"], "test_image_count": len(test_data)}, "environment": {"python": platform.python_version(), "torch": torch.__version__, "cuda_available": torch.cuda.is_available(), "cuda_version": torch.version.cuda, "device": str(device)}, "training_duration_seconds": round(time.monotonic() - started, 2), "evaluated_at_utc": datetime.now(timezone.utc).isoformat()}
    (output_dir / "config.json").write_text(json.dumps(config.to_dict(), indent=2), encoding="utf-8"); (output_dir / "label_mapping.json").write_text(json.dumps(label_mapping, indent=2), encoding="utf-8"); (output_dir / "training_history.json").write_text(json.dumps(history, indent=2), encoding="utf-8"); (output_dir / "metrics.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Train CycloneAI's event-split intensity baseline")
    parser.add_argument("--manifest", type=Path, required=True); parser.add_argument("--label-mapping", type=Path, required=True); parser.add_argument("--output-dir", type=Path, default=Path("../models/intensity")); parser.add_argument("--backbone", choices=("resnet18", "resnet50"), default="resnet18"); parser.add_argument("--epochs", type=int, default=20); parser.add_argument("--batch-size", type=int, default=16); parser.add_argument("--learning-rate", type=float, default=1e-4); parser.add_argument("--image-size", type=int, default=224); parser.add_argument("--seed", type=int, default=42); parser.add_argument("--dataset-version", required=True); parser.add_argument("--dataset-source", required=True); parser.add_argument("--timestamp-tolerance-minutes", type=int, default=30); parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto"); parser.add_argument("--no-pretrained", action="store_true")
    args = parser.parse_args()
    config = IntensityConfig(backbone=args.backbone, image_size=args.image_size, batch_size=args.batch_size, epochs=args.epochs, learning_rate=args.learning_rate, seed=args.seed, dataset_version=args.dataset_version, dataset_source=args.dataset_source, timestamp_tolerance_minutes=args.timestamp_tolerance_minutes, pretrained=not args.no_pretrained)
    print(json.dumps(train(config, manifest_path=args.manifest, label_mapping_path=args.label_mapping, output_dir=args.output_dir, device_name=args.device), indent=2))


if __name__ == "__main__": main()
