# MP2B Extension for Blender

MP2B Extension is a Blender add-on designed to work together with **MP2B Client**.

It receives **real-time tracking data and video streams** over the network and applies them directly inside Blender for real-time animation, visualization, and interaction.

---

## How it works

MP2B is split into two separate components:

- **MP2B Client**  
  A standalone application responsible for:
  - system camera access
  - video capture
  - AI tracking (MediaPipe: pose, face, hands)

- **MP2B Extension (this add-on)**  
  A Blender add-on responsible for:
  - receiving tracking data via UDP
  - ingesting video streams from the client (Shared Memory or MJPEG)
  - applying tracking data and video inside Blender

---

## Privacy & Data Handling

The MP2B Extension:

- **does NOT access system cameras or hardware devices**
- **does NOT perform any local camera or device capture**
- **does NOT collect, store, or transmit user data**

The extension only **ingests video streams provided by MP2B Client**  
(via **Shared Memory (SHM)** or **MJPEG network streams**) and displays them inside Blender.

All **camera handling, video capture, and AI tracking** are performed exclusively by **MP2B Client**, which runs as a separate application.

---

## License

MP2B Extension is licensed under the  
**GNU General Public License v3.0 or later (GPL-3.0-or-later)**.

This extension bundles third-party Python libraries (wheels), which are licensed
under their respective licenses (MIT, Apache 2.0, BSD, etc.).

For full license details, see `THIRD_PARTY_LICENSES.txt`.

---

## Notes

- This add-on does **not** require internet access.
- The extension can be safely removed at any time by uninstalling it from Blender.
