# Hand Mouse

Control your computer's mouse pointer with hand gestures using a webcam.

**Author:** Matin Sobhani  
**Version:** 7.0.0  
**Platform:** Windows

## Features

- Webcam-based hand tracking with MediaPipe Tasks
- Cursor movement using palm position
- Left click and double-click gestures
- Right click gesture
- Scroll using a V-shaped hand gesture
- Drag and drop using a fist or fingertip pinch gesture
- Multi-monitor support
- Adjustable cursor sensitivity and smoothing
- Hand-tremor stabilization
- Settings saved between launches
- Camera and runtime error dialogs

## Gesture controls

| Gesture | Action |
|---|---|
| Move an open palm | Move the cursor |
| Pinch thumb and index finger, then release | Left click |
| Pinch thumb and index finger twice quickly | Double-click |
| Pinch thumb and middle finger | Right click |
| Hold a V gesture (index and middle fingers open) | Scroll |
| Pinch all four fingertips to the thumb, or make a fist | Drag |

## Download

Download the Windows executable from the **Releases** section of this repository.

On the first launch, the application downloads the MediaPipe hand-landmarker model (approximately 7 MB). An internet connection is required unless the model is bundled with the executable.

## Run from source

Use 64-bit Python on Windows.

```bash
python -m venv .venv
.venv\\Scripts\\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python hand_mouse.py
```

## Build the Windows executable

Install the dependencies, download `hand_landmarker.task` if you want to bundle the model, then run:

```bash
python -m PyInstaller --noconfirm --clean --onefile --windowed --name HandMouse --collect-all mediapipe --add-data "hand_landmarker.task:." hand_mouse.py
```

The executable will be created in the `dist` directory.

If you do not want to bundle `hand_landmarker.task`, omit the `--add-data` argument. The application will download the model on first launch.

## Privacy

Camera frames are processed locally by the application using MediaPipe. The source code does not intentionally upload camera frames or hand-tracking data to a server. The hand-landmarker model is downloaded from Google's MediaPipe model hosting endpoint on first launch.

## Troubleshooting

- **Camera not detected:** Close other apps that may be using the webcam and check Windows camera privacy permissions.
- **Model download fails:** Check your internet connection, or place a valid `hand_landmarker.task` file beside the executable.
- **Mouse movement is unstable:** Adjust the sensitivity, smoothing, and stabilization settings.
- **Dragging does not work in an application:** Try enabling **Real mouse input** in the settings.

## Project status

This project is shared for personal use, experimentation, and feedback. Test the executable on your own Windows setup before relying on it for important work.

## License

No license has been selected for this repository yet. Add a license file before describing the project as open source.
