import os
from slideshow import constants

def level_of(path):
    return len([item for item in path.split(os.sep) if item != ""])

def truncate_path(path, levels_up):
    """Truncate the path based on the balance level."""
    return "\\".join(
        path.split("\\")[
            : ((level_of(path) - levels_up) if levels_up < 0 else levels_up)
        ]
    )
    
def contains_subdirectory(path):
    for root, directories, files in os.walk(path):
        if directories:
            return len(directories)
    return False

def contains_files(path):
    for root, directories, files in os.walk(path):
        if files:
            return True
    return False

def is_textfile(file):
    return file.lower().endswith(constants.TEXT_FILES)


def is_imagefile(file):
    return file.lower().endswith(constants.IMAGE_FILES)

def is_videofile(file):
    return file.lower().endswith(constants.VIDEO_FILES)

def is_videoallowed(data_video, defaults):
    if data_video is False:
        return False
    if defaults.args_video is not None:
        return defaults.args_video
    else:
        return data_video if data_video is not None else defaults.video

