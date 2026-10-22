# Portrait media

Four looping videos, two per theme. The landing page uses them as a pair: the masked portrait is
the base, and the plain portrait (no mask, shows what is behind it) is revealed inside the
cursor spotlight, so the two must be the same length and framing.

| File | Source in `portrait-source/` |
| --- | --- |
| `base-light.mp4` | `maksidom-masked-white-sync.mp4` |
| `reveal-light.mp4` | `maksidom-plain-white-sync.mp4` |
| `base-dark.mp4` | `maksidom-masked-dark-sync (1).mp4` |
| `reveal-dark.mp4` | `maksidom-plain-dark-sync.mp4` |

Any missing file falls back to the still photos from the brief. To shrink a file:

    ffmpeg -i in.mp4 -an -vf scale=1920:-2 -c:v libx264 -crf 26 -preset slow -movflags +faststart out.mp4
