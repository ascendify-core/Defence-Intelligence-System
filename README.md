# Image Intelligence Extraction System

Extracts **metadata + detects objects** from JPEG images.
Produces two structured JSON reports ready for downstream analysis or dashboards.

---

## Features

### Metadata Extraction (`image_analysis.json`)
| Field | Details |
|---|---|
| Filename | Original filename |
| SHA-256 hash | File integrity fingerprint |
| File size | Human-readable + bytes |
| Timestamps | File modified/created, EXIF captured/digitized |
| Resolution | Width × Height, Megapixels, Aspect ratio |
| GPS Data | Lat/Lon (decimal degrees), Altitude, Speed, Google Maps URL |
| Device Info | Camera make, model, software |
| Camera Settings | ISO, aperture, shutter speed, focal length, flash, white balance |
| Color | Color space, mode |

### Object Detection (`image_objects.json`)
| Category | Examples |
|---|---|
| `person` | People, soldiers, crowds |
| `vehicle` | Cars, trucks, buses, motorcycles |
| `aircraft` | Airplanes, helicopters, drones (via GroundingDINO) |
| `ship` | Boats, vessels, warships |
| `building` | Houses, skyscrapers, bridges (via GroundingDINO) |
| `weapon` | Knives; guns/missiles via GroundingDINO |
| `logo` | Signs, emblems, flags (via GroundingDINO) |

Each detection includes bounding box (pixels + normalised), confidence score, and source model.

---

## Setup

### 1. Install Python 3.10+
Download from [python.org](https://python.org).

### 2. Clone / download this project
```
image_intelligence/
├── main.py
├── requirements.txt
├── README.md
└── utils/
    ├── metadata_extractor.py
    ├── object_detector.py
    ├── report_writer.py
    └── ui.py
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. (Optional) Install GroundingDINO for richer detection
Uncomment the `groundingdino-py` line in `requirements.txt`, then:
```bash
pip install groundingdino-py
```
GroundingDINO downloads ~700 MB of model weights on first run.

---

## Usage

### A — Interactive file picker (recommended for VS Code)
```bash
python main.py
```
A file-picker dialog will open. Select one or more JPEG files and click Open.

### B — Pass files directly on the command line
```bash
python main.py photo1.jpg photo2.jpg /path/to/photo3.jpeg
```

### C — Process an entire folder
```bash
python main.py --folder ./my_images
```

### D — With all options
```bash
python main.py \
  --folder ./my_images \
  --output-dir ./reports \
  --model yolo11m.pt \
  --confidence 0.40 \
  --grounding-dino
```

---

## Command-Line Options

| Flag | Default | Description |
|---|---|---|
| `images` | (positional) | JPEG file paths |
| `--folder / -f` | — | Process all JPEGs in a folder |
| `--output-dir / -o` | `./output` | Where to write JSON outputs |
| `--model / -m` | `yolo11n.pt` | YOLOv11 weights (n/s/m/l/x) |
| `--confidence / -c` | `0.35` | Detection confidence threshold |
| `--no-annotated` | false | Skip saving annotated images |
| `--grounding-dino` | false | Enable GroundingDINO for richer detection |

### Model size guide
| Model | Speed | Accuracy | Use case |
|---|---|---|---|
| `yolo11n.pt` | Fastest | Good | Quick scans, many images |
| `yolo11s.pt` | Fast | Better | Balanced |
| `yolo11m.pt` | Medium | Strong | Recommended default |
| `yolo11l.pt` | Slow | High | High-accuracy work |
| `yolo11x.pt` | Slowest | Highest | Maximum precision |

Models download automatically from Ultralytics on first run (~few MB to ~100 MB).

---

## Outputs

```
output/
├── image_analysis.json     ← Metadata for all images
├── image_objects.json      ← Object detections for all images
└── annotated/
    ├── annotated_photo1.jpg
    └── annotated_photo2.jpg
```

### image_analysis.json — example entry
```json
{
  "filename": "patrol.jpg",
  "file_size_human": "2.3 MB",
  "sha256": "a3f9...",
  "timestamp": {
    "captured": "2024-03-15T14:32:10",
    "file_modified": "2024-03-15T14:32:11"
  },
  "resolution": {
    "width": 4032,
    "height": 3024,
    "megapixels": 12.19,
    "aspect_ratio": "4:3"
  },
  "gps": {
    "latitude": 10.5277,
    "longitude": 76.2144,
    "altitude_meters": 53.0,
    "google_maps_url": "https://maps.google.com/?q=10.5277,76.2144"
  },
  "device": {
    "make": "Apple",
    "model": "iPhone 15 Pro",
    "software": "17.3.1"
  }
}
```

### image_objects.json — example entry
```json
{
  "filename": "patrol.jpg",
  "total_detections": 4,
  "category_summary": { "person": 3, "vehicle": 1 },
  "intelligence_flags": {
    "has_people": true,
    "has_vehicles": true,
    "has_weapons": false,
    "person_count": 3,
    "vehicle_count": 1,
    "risk_level": "MEDIUM"
  },
  "detections": [
    {
      "source": "YOLOv11",
      "label": "person",
      "category": "person",
      "confidence": 0.891,
      "bbox_pixels": { "x1": 120, "y1": 80, "x2": 250, "y2": 420 },
      "bbox_normalized": { "x1": 0.03, "y1": 0.026, "x2": 0.062, "y2": 0.139 },
      "area_fraction": 0.003
    }
  ],
  "processing_time_seconds": 0.312
}
```

---

## VS Code Tips

1. Open the `image_intelligence/` folder in VS Code.
2. Open the integrated terminal: `Ctrl+`` ` (backtick).
3. Run `python main.py` — the file picker will appear.
4. After processing, open `output/image_analysis.json` and use the JSON viewer extension for easy reading.

Recommended VS Code extensions:
- **Python** (Microsoft)
- **JSON Viewer** (for pretty-printing outputs)
- **Prettier** (optional, auto-formats JSON)

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `No module named 'ultralytics'` | Run `pip install ultralytics` |
| File picker doesn't open | Use CLI: `python main.py photo.jpg` |
| `No EXIF data found` | Image has been stripped of EXIF (common on social media downloads) |
| Low detection accuracy | Use a larger model: `--model yolo11m.pt` or `yolo11l.pt` |
| CUDA out of memory | The model falls back to CPU automatically |
| GroundingDINO not detecting | Install: `pip install groundingdino-py` and add `--grounding-dino` flag |
