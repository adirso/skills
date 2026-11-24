"""Wedding Album Curator backend."""
import os as _os

# Quiet native-library logging (OpenCV DNN, MediaPipe/TFLite) unless the user overrides it.
_os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")
_os.environ.setdefault("GLOG_minloglevel", "2")
_os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
