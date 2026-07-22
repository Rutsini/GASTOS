import os


def is_allowed_file(filename, allowed_extensions):
    _, extension = os.path.splitext(filename or "")
    return extension.lower() in allowed_extensions
