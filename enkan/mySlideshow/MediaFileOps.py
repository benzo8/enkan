import logging
import os
from dataclasses import dataclass

from PIL import Image

logger = logging.getLogger("enkan.ui")

ORIENTATION_TO_CW: dict[int, int] = {1: 0, 3: 180, 6: 90, 8: 270}
CW_TO_ORIENTATION: dict[int, int] = {
    value: key for key, value in ORIENTATION_TO_CW.items()
}


@dataclass(frozen=True)
class ExifWriteResult:
    new_orientation: int | None
    warning_title: str | None = None
    warning_message: str | None = None


def delete_media_file(path: str) -> None:
    os.remove(path)


def write_exif_orientation(image_path: str, rotation_angle: int | float) -> ExifWriteResult:
    orientation_tag = 0x0112
    rotation_cw = (-rotation_angle) % 360
    if rotation_cw % 90 != 0:
        logger.error(
            "EXIF update aborted: rotation %s deg is not a multiple of 90 for %s.",
            rotation_angle,
            image_path,
        )
        return ExifWriteResult(new_orientation=None)

    with Image.open(image_path) as img:
        exif = img.getexif()
        if exif is None:
            if hasattr(Image, "Exif"):
                exif = Image.Exif()
            else:
                logger.warning(
                    "EXIF update skipped for %s: Pillow build lacks Exif support.",
                    image_path,
                )
                return ExifWriteResult(new_orientation=None)
        if not hasattr(exif, "tobytes"):
            logger.warning(
                "EXIF update skipped for %s: Pillow Exif object has no tobytes().",
                image_path,
            )
            return ExifWriteResult(new_orientation=None)

        current_orientation = exif.get(orientation_tag, 1)
        base_cw = ORIENTATION_TO_CW.get(current_orientation, 0)
        new_cw = (base_cw + rotation_cw) % 360
        new_orientation = CW_TO_ORIENTATION.get(new_cw, 1)
        exif[orientation_tag] = new_orientation
        exif_bytes = exif.tobytes() if hasattr(exif, "tobytes") else None
        save_kwargs = {"exif": exif_bytes} if exif_bytes else {}
        try:
            img.save(image_path, **save_kwargs)
        except PermissionError as err:
            logger.warning("EXIF update failed (permission) for %s: %s", image_path, err)
            return ExifWriteResult(
                new_orientation=None,
                warning_title="Permission Denied",
                warning_message=(
                    "Could not save the updated rotation because access was denied."
                ),
            )
        except OSError as err:
            logger.warning("EXIF update failed for %s: %s", image_path, err)
            return ExifWriteResult(
                new_orientation=None,
                warning_title="Save Failed",
                warning_message="Could not write the updated rotation to this file.",
            )

    return ExifWriteResult(new_orientation=new_orientation)
