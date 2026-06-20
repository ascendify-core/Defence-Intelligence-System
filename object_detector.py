"""
Object Detector
===============
Runs YOLOv11 (primary) and optionally GroundingDINO (open-vocabulary)
to detect objects of intelligence interest in images.

Target categories:
  People, Vehicles, Aircraft, Ships, Buildings, Weapons, Logos
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np


# ── YOLOv11 COCO class → intelligence category mapping ────────────────────────
# YOLOv11 is trained on COCO (80 classes). We map COCO labels → our categories.
YOLO_CATEGORY_MAP: dict[str, str] = {
    # People
    "person": "person",
    # Vehicles (ground)
    "car": "vehicle", "truck": "vehicle", "bus": "vehicle",
    "motorcycle": "vehicle", "bicycle": "vehicle",
    "train": "vehicle",
    # Vehicles (air)
    "airplane": "aircraft",
    # Vehicles (sea)
    "boat": "ship",
    # Buildings / infrastructure (COCO doesn't have "building" — handled via GroundingDINO)
    # Animals (useful for scene context)
    "horse": "animal", "cow": "animal", "sheep": "animal", "dog": "animal", "cat": "animal",
    # Weapons / military (COCO is limited here — GroundingDINO fills in)
    "knife": "weapon", "scissors": "weapon",
    # Tools / equipment
    "cell phone": "tool", "laptop": "tool", "keyboard": "tool",
    "backpack": "tool", "handbag": "tool", "suitcase": "tool",
    "umbrella": "tool",
    # Other
    "traffic light": "infrastructure", "fire hydrant": "infrastructure",
    "stop sign": "infrastructure", "parking meter": "infrastructure",
    "bench": "infrastructure",
    "chair": "furniture", "couch": "furniture", "dining table": "furniture",
    "bed": "furniture",
    "tv": "electronics", "microwave": "electronics", "oven": "electronics",
    "refrigerator": "electronics",
    "sports ball": "sports", "kite": "sports", "frisbee": "sports",
    "skis": "sports", "snowboard": "sports", "surfboard": "sports",
    "tennis racket": "sports",
    "bottle": "object", "wine glass": "object", "cup": "object",
    "fork": "object", "spoon": "object", "bowl": "object",
    "banana": "food", "apple": "food", "sandwich": "food", "orange": "food",
    "broccoli": "food", "carrot": "food", "hot dog": "food",
    "pizza": "food", "donut": "food", "cake": "food",
    "potted plant": "vegetation",
    "vase": "object", "clock": "object", "book": "object",
    "toothbrush": "object", "hair drier": "object",
    "teddy bear": "object",
}

# GroundingDINO open-vocabulary prompts for categories YOLO may miss
GROUNDING_DINO_PROMPTS = [
    "person . people . soldier . crowd",
    "car . truck . bus . motorcycle . vehicle",
    "airplane . helicopter . drone . aircraft . jet",
    "ship . boat . vessel . submarine . warship",
    "building . house . skyscraper . structure . bridge",
    "gun . rifle . pistol . weapon . missile . tank",
    "logo . sign . emblem . badge . flag",
]


class ObjectDetector:
    """
    Runs object detection using YOLOv11 and (optionally) GroundingDINO.
    """

    def __init__(
        self,
        model_name: str = "yolo11n.pt",
        confidence: float = 0.35,
        save_annotated: bool = True,
        annotated_dir: Path | None = None,
        use_grounding_dino: bool = False,
    ):
        self.confidence = confidence
        self.save_annotated = save_annotated
        self.annotated_dir = annotated_dir
        self.use_grounding_dino = use_grounding_dino
        self._gdino = None

        # Load YOLO
        self.yolo = None
        print(f"\n  Loading YOLOv11 model: {model_name}")
        try:
            from ultralytics import YOLO
            self.yolo = YOLO(model_name)
            print(f"  YOLOv11 ready ✓")
        except Exception as e:
            print(f"  [ERROR] Could not load YOLO model '{model_name}': {e}")
            print(f"  [INFO] Ensure you have an internet connection so Ultralytics can download the model.")
            print(f"  [INFO] Alternatively, download manually from:")
            print(f"         https://github.com/ultralytics/assets/releases")
            print(f"         and place '{model_name}' in the project directory.")
            raise

        # Optionally load GroundingDINO
        if use_grounding_dino:
            self._load_grounding_dino()

        if save_annotated and annotated_dir:
            annotated_dir.mkdir(parents=True, exist_ok=True)

    def _load_grounding_dino(self):
        try:
            from groundingdino.util.inference import load_model, load_image, predict
            import groundingdino
            gdino_dir = Path(groundingdino.__file__).parent
            cfg = gdino_dir / "config" / "GroundingDINO_SwinT_OGC.py"
            weights = "groundingdino_swint_ogc.pth"
            if not Path(weights).exists():
                print("  [INFO] Downloading GroundingDINO weights (~700 MB)...")
                import urllib.request
                url = "https://github.com/IDEA-Research/GroundingDINO/releases/download/v0.1.0-alpha/groundingdino_swint_ogc.pth"
                urllib.request.urlretrieve(url, weights)
            self._gdino = {
                "model": load_model(str(cfg), weights),
                "predict": predict,
                "load_image": load_image,
            }
            print("  GroundingDINO ready ✓")
        except ImportError:
            print("  [WARN] GroundingDINO not installed. Run: pip install groundingdino-py")
            self.use_grounding_dino = False
        except Exception as e:
            print(f"  [WARN] GroundingDINO failed to load: {e}")
            self.use_grounding_dino = False

    def detect(self, image_path: Path) -> dict:
        t0 = time.perf_counter()

        # Load image
        img_bgr = cv2.imread(str(image_path))
        if img_bgr is None:
            return {
                "filename": image_path.name,
                "error": "Could not read image with OpenCV.",
                "detections": [],
                "total_detections": 0,
            }

        h, w = img_bgr.shape[:2]
        detections: list[dict] = []

        # ── YOLOv11 ───────────────────────────────────────────────────────────
        yolo_detections, annotated = self._run_yolo(img_bgr, image_path)
        detections.extend(yolo_detections)

        # ── GroundingDINO ─────────────────────────────────────────────────────
        gdino_detections = []
        if self.use_grounding_dino and self._gdino:
            gdino_detections = self._run_grounding_dino(image_path, w, h)
            detections.extend(gdino_detections)
            # Draw GDINO boxes onto annotated image
            if annotated is not None:
                for d in gdino_detections:
                    x1, y1, x2, y2 = d["bbox_pixels"]["x1"], d["bbox_pixels"]["y1"], \
                                      d["bbox_pixels"]["x2"], d["bbox_pixels"]["y2"]
                    cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 165, 255), 2)
                    lbl = f"[DINO] {d['label']} {d['confidence']:.2f}"
                    cv2.putText(annotated, lbl, (x1, max(y1 - 5, 10)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 165, 255), 1)

        # ── Save annotated image ──────────────────────────────────────────────
        annotated_path = None
        if self.save_annotated and annotated is not None and self.annotated_dir:
            out_name = f"annotated_{image_path.stem}.jpg"
            annotated_path = str(self.annotated_dir / out_name)
            cv2.imwrite(annotated_path, annotated)

        elapsed = time.perf_counter() - t0

        # ── Build category summary ────────────────────────────────────────────
        category_counts: dict[str, int] = {}
        for d in detections:
            cat = d.get("category", "unknown")
            category_counts[cat] = category_counts.get(cat, 0) + 1

        intelligence_flags = _intelligence_flags(detections)

        return {
            "filename": image_path.name,
            "filepath": str(image_path.resolve()),
            "image_dimensions": {"width": w, "height": h},
            "total_detections": len(detections),
            "category_summary": category_counts,
            "intelligence_flags": intelligence_flags,
            "detections": detections,
            "annotated_image": annotated_path,
            "processing_time_seconds": round(elapsed, 3),
            "models_used": (
                ["YOLOv11", "GroundingDINO"] if gdino_detections else ["YOLOv11"]
            ),
        }

    def _run_yolo(self, img_bgr: np.ndarray, image_path: Path) -> tuple[list[dict], np.ndarray]:
        results = self.yolo(img_bgr, conf=self.confidence, verbose=False)

        detections: list[dict] = []
        annotated = None

        for result in results:
            # Render annotated frame
            annotated = result.plot()  # returns BGR numpy array

            boxes = result.boxes
            if boxes is None:
                continue

            h, w = img_bgr.shape[:2]
            for box in boxes:
                cls_id = int(box.cls[0])
                label = self.yolo.names[cls_id]
                conf = float(box.conf[0])

                # Bounding box in pixels
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)

                # Normalised bbox
                nx1, ny1 = x1 / w, y1 / h
                nx2, ny2 = x2 / w, y2 / h
                bw, bh = (x2 - x1) / w, (y2 - y1) / h

                category = YOLO_CATEGORY_MAP.get(label, "object")

                detections.append({
                    "source": "YOLOv11",
                    "label": label,
                    "category": category,
                    "confidence": round(conf, 4),
                    "bbox_pixels": {"x1": x1, "y1": y1, "x2": x2, "y2": y2},
                    "bbox_normalized": {
                        "x1": round(nx1, 4), "y1": round(ny1, 4),
                        "x2": round(nx2, 4), "y2": round(ny2, 4),
                        "width": round(bw, 4), "height": round(bh, 4),
                    },
                    "area_fraction": round(bw * bh, 4),
                })

        return detections, annotated

    def _run_grounding_dino(self, image_path: Path, w: int, h: int) -> list[dict]:
        detections: list[dict] = []
        gdino = self._gdino

        for prompt in GROUNDING_DINO_PROMPTS:
            try:
                _, img_tensor = gdino["load_image"](str(image_path))
                boxes, logits, phrases = gdino["predict"](
                    model=gdino["model"],
                    image=img_tensor,
                    caption=prompt,
                    box_threshold=self.confidence,
                    text_threshold=self.confidence,
                )
                for box, logit, phrase in zip(boxes, logits, phrases):
                    cx, cy, bw, bh = box.tolist()
                    x1 = int((cx - bw / 2) * w)
                    y1 = int((cy - bh / 2) * h)
                    x2 = int((cx + bw / 2) * w)
                    y2 = int((cy + bh / 2) * h)

                    # Map phrase to category
                    category = _phrase_to_category(phrase)

                    detections.append({
                        "source": "GroundingDINO",
                        "label": phrase.strip(),
                        "category": category,
                        "confidence": round(float(logit), 4),
                        "bbox_pixels": {"x1": x1, "y1": y1, "x2": x2, "y2": y2},
                        "bbox_normalized": {
                            "x1": round(x1 / w, 4), "y1": round(y1 / h, 4),
                            "x2": round(x2 / w, 4), "y2": round(y2 / h, 4),
                            "width": round(bw, 4), "height": round(bh, 4),
                        },
                        "area_fraction": round(bw * bh, 4),
                    })
            except Exception as e:
                pass  # silently skip failed prompts

        return detections


def _phrase_to_category(phrase: str) -> str:
    phrase = phrase.lower()
    if any(w in phrase for w in ("person", "people", "soldier", "crowd", "man", "woman", "child")):
        return "person"
    if any(w in phrase for w in ("airplane", "helicopter", "drone", "aircraft", "jet")):
        return "aircraft"
    if any(w in phrase for w in ("ship", "boat", "vessel", "submarine", "warship")):
        return "ship"
    if any(w in phrase for w in ("building", "house", "skyscraper", "structure", "bridge")):
        return "building"
    if any(w in phrase for w in ("gun", "rifle", "pistol", "weapon", "missile", "tank", "bomb")):
        return "weapon"
    if any(w in phrase for w in ("logo", "sign", "emblem", "badge", "flag")):
        return "logo"
    if any(w in phrase for w in ("car", "truck", "bus", "motorcycle", "vehicle")):
        return "vehicle"
    return "object"


def _intelligence_flags(detections: list[dict]) -> dict:
    """Summarise high-interest intelligence signals."""
    cats = [d.get("category") for d in detections]
    flags = {
        "has_people": "person" in cats,
        "has_vehicles": "vehicle" in cats,
        "has_aircraft": "aircraft" in cats,
        "has_ships": "ship" in cats,
        "has_buildings": "building" in cats,
        "has_weapons": "weapon" in cats,
        "has_logos": "logo" in cats,
        "person_count": cats.count("person"),
        "vehicle_count": cats.count("vehicle"),
        "aircraft_count": cats.count("aircraft"),
        "ship_count": cats.count("ship"),
    }
    # Risk level heuristic
    risk = "LOW"
    if flags["has_weapons"]:
        risk = "HIGH"
    elif flags["has_aircraft"] or flags["has_ships"]:
        risk = "MEDIUM"
    elif flags["has_people"] and flags["has_vehicles"]:
        risk = "MEDIUM"
    flags["risk_level"] = risk
    return flags
