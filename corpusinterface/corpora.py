from pathlib import Path
from abc import ABC, abstractmethod
import os
import io
import re
import json
import ast
import zipfile
import tarfile

import pandas


class Corpus(ABC):
    """An abstract base class for data items, such as corpora or documents."""

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
        return False

    def open(self):
        """Open resources owned by the corpus."""
        pass

    def close(self):
        """Close resources owned by the corpus."""
        pass

    def metadata(self, *args, **kwargs):
        return None

    @abstractmethod
    def data(self, *args, **kwargs):
        raise NotImplementedError


class FileCorpusBase(Corpus):
    """A collection of file-like objects in a directory-like object (e.g., normal files or a zip archive)."""

    # special keyword arguments
    __META_READER__ = "meta_reader"
    __FILE_READER__ = "file_reader"

    class LazyLoad:
        """Simple wrapper for lazy-loading of data using a provided loading function."""

        def __init__(self, load_func, *args, **kwargs):
            self.load_func = load_func
            self.args = args
            self.kwargs = kwargs
            self.data = None

        def load(self):
            if self.data is None:
                self.data = self.load_func(*self.args, **self.kwargs)
            return self.data

    def __init__(self, *,
                 path,
                 include_dirs=False,
                 file_regex=None,
                 path_regex=None,
                 file_exclude_regex=None,
                 path_exclude_regex=None,
                 **kwargs):
        # set path and check
        self._path = Path(path)
        if not self._path.exists():
            raise FileNotFoundError(f"Corpus path '{self._path}' does not exist")
        # whether to include directories when iterating over the corpus
        self.include_dirs = include_dirs
        # remember additional keyword arguments
        self.kwargs = kwargs
        # initialise regex for including files
        if file_regex is None:
            self.file_regex = None
        else:
            self.file_regex = re.compile(file_regex)
        # initialise regex for including paths
        if path_regex is None:
            self.path_regex = None
        else:
            self.path_regex = re.compile(path_regex)
        # initialise regex for excluding files
        if file_exclude_regex is None:
            self.file_exclude_regex = None
        else:
            self.file_exclude_regex = re.compile(file_exclude_regex)
        # initialise regex for excluding paths
        if path_exclude_regex is None:
            self.path_exclude_regex = None
        else:
            self.path_exclude_regex = re.compile(path_exclude_regex)

    def __repr__(self):
        return f"{self.__class__.__name__}({self._path})"

    def _skip_file(self, file_name, file_path):
        # check file inclusion regex
        if self.file_regex is not None and not self.file_regex.match(file_name):
            return True  # skip non-matching files
        # check path inclusion regex
        if self.path_regex is not None and not self.path_regex.match(file_path):
            return True  # skip non-matching paths
        # check file exclusion regex
        if self.file_exclude_regex is not None and self.file_exclude_regex.match(file_name):
            return True  # skip matching files
        # check path exclusion regex
        if self.path_exclude_regex is not None and self.path_exclude_regex.match(file_path):
            return True  # skip matching paths
        return False

    @abstractmethod
    def files(self):
        """Return an iterator over the files in the corpus."""
        raise NotImplementedError

    def metadata(self, *args, **kwargs):
        kwargs = {**self.kwargs, **kwargs}
        meta_reader = kwargs.get(self.__META_READER__, None)
        if meta_reader is None:
            return self._path
        else:
            return meta_reader(self._path, *args, **kwargs)

    def data(self, *args, **kwargs):
        kwargs = {**dict(return_files=False, lazy_load=False), **self.kwargs, **kwargs}
        return_files = kwargs.pop('return_files')
        lazy_load = kwargs.pop('lazy_load')
        file_reader = kwargs.get(self.__FILE_READER__, None)
        if file_reader is None:
            raise TypeError(f"{self.__FILE_READER__} is None; provide file_reader or use files() if you want to iterate over the files instead")
        if not callable(file_reader):
            raise TypeError(f"{self.__FILE_READER__} must be a callable, not '{file_reader}' of type {type(file_reader)}")
        for file_path in self.files():
            if lazy_load:
                d = self.LazyLoad(file_reader, file_path, *args, **kwargs)
            else:
                d = file_reader(file_path, *args, **kwargs)
            if return_files:
                yield file_path, d
            else:
                yield d


class PathLike(ABC):
    """
    An abstract base class for path-like objects that behave roughly like pathlib.Path. They are NOT guaranteed to
    exist as real paths in the filesystem (e.g., they could be files within a zip archive) and therefore do not
    implement the os.PathLike API.
    """

    def __repr__(self):
        return f"{self.__class__.__name__}('{self.path}')"

    def __str__(self):
        return str(self.path)

    @property
    @abstractmethod
    def name(self):
        """Name of the file or directory the path points to."""
        raise NotImplementedError

    @property
    @abstractmethod
    def path(self):
        """Full path to the file or directory the path points to."""
        raise NotImplementedError

    @abstractmethod
    def open(self, mode='r'):
        """Open the file the path points to."""
        raise NotImplementedError


class FileCorpus(FileCorpusBase):
    """A collection of normal files in a directory"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # check if path is a directory
        if not self._path.is_dir():
            raise NotADirectoryError(f"{self._path} is not a directory")

    def files(self):
        # recursively traverse directory
        for root, dirs, files in os.walk(self._path):
            root = Path(root)
            for file_name in files:
                file_path = root / file_name
                if self._skip_file(file_name, str(file_path)):
                    continue
                if file_path.is_dir() and not self.include_dirs:
                    continue
                yield RealPath(file_path)


class RealPath(PathLike, os.PathLike):
    """
    Class representing a real path. This is a subclass of PathLike and os.PathLike to make it compatible with both
    standard os.PathLike objects and virtual paths in archive files (e.g., ZipFile, TarFile).
    """

    def __init__(self, path):
        self._path = Path(path)

    def __fspath__(self):
        return os.fspath(self._path)

    @property
    def name(self):
        return self._path.name

    @property
    def path(self):
        return self._path

    def open(self, mode='r'):
        return self._path.open(mode)


class ArchiveCorpusBase(FileCorpusBase):
    def __init__(self, path, file=None, **kwargs):
        path = Path(path)
        if file is not None:
            path /= Path(file)
        super().__init__(path=path, **kwargs)
        if not self._path.is_file():
            raise FileNotFoundError(f"'{self._path}' is not an archive file")
        self._archive = None


class ZipFileCorpus(ArchiveCorpusBase):

    def open(self) -> None:
        if self._archive is not None:
            raise RuntimeError("Archive is already open")
        self._archive = zipfile.ZipFile(self._path, mode="r")

    def close(self) -> None:
        if self._archive is not None:
            self._archive.close()
            self._archive = None

    def files(self):
        if self._archive is None:
            raise RuntimeError("Archive must be opened before iteration")
        for info in self._archive.infolist():
            file_name = Path(info.filename).name
            file_path = self._path / Path(info.filename)

            if self._skip_file(str(file_name), str(file_path)):
                continue

            if info.is_dir() and not self.include_dirs:
                continue

            yield ZipEntry(self, info)


class ZipEntry(PathLike):

    def __init__(self, archive, info):
        self._archive = archive
        self._info = info

    @property
    def name(self):
        return Path(self._info.filename).name

    @property
    def path(self):
        return self._archive._path / Path(self._info.filename)

    def open(self, mode="r", **kwargs):
        binary = self._archive._archive.open(self._info, "r")
        if mode == "rb":
            return binary
        elif mode in ("r", "rt"):
            kwargs.setdefault('encoding', "utf-8")
            return io.TextIOWrapper(binary, **kwargs)
        else:
            raise ValueError(f"Unsupported mode: {mode}")


class TarFileCorpus(ArchiveCorpusBase):

    def open(self):
        if self._archive is not None:
            raise RuntimeError("Archive is already open")

        # Automatically detects .tar, .tar.gz, .tgz, .tar.bz2, .tar.xz, etc.
        self._archive = tarfile.open(self._path, mode="r:*")

    def close(self):
        if self._archive is not None:
            self._archive.close()
            self._archive = None

    def files(self):
        if self._archive is None:
            raise RuntimeError("Archive must be opened before iteration")

        for info in self._archive.getmembers():
            file_name = Path(info.name).name
            file_path = self._path / Path(info.name)

            if self._skip_file(str(file_name), str(file_path)):
                continue

            if info.isdir() and not self.include_dirs:
                continue

            # Skip entries such as symbolic links and device files.
            if not info.isfile() and not info.isdir():
                continue

            yield TarEntry(self, info)


class TarEntry(PathLike):

    def __init__(self, archive, info):
        self._archive = archive
        self._info = info

    @property
    def name(self):
        return Path(self._info.name).name

    @property
    def path(self):
        return self._archive._path / Path(self._info.name)

    def open(self, mode="r", **kwargs):
        binary = self._archive._archive.extractfile(self._info)

        if binary is None:
            raise OSError(f"Could not open archive entry: {self.path}")

        if mode == "rb":
            return binary
        elif mode in ("r", "rt"):
            kwargs.setdefault('encoding', "utf-8")
            return io.TextIOWrapper(binary, **kwargs)
        else:
            raise ValueError(f"Unsupported mode: {mode}")


# single file corpora
# -------------------

class SingleFileCorpus(Corpus):
    """
    A corpus consisting of a single file, superclass for different file types.
    
    Can be loaded using its constructor, which takes the arguments path, file, and corpus_kwargs.
    path and file refer to the path of corpus directory and the single file containing the data respectively.
    corpus_kwargs contains any keyword arguments that should be used for reading the data,
    e.g. the file_reader and its arguments.
    """

    def __init__(self, path=None, file=None, corpus_kwargs={}, **kwargs):
        # check if path and file are supplied
        if path is None:
            raise TypeError("Missing required key 'path'")
        if file is None:
            raise TypeError("Missing required key 'file'")

        # register path to file and check if exists
        self.path = Path(path).resolve() / Path(file)
        if not self.path.exists():
            raise FileNotFoundError(f"Corpus file {self.path} does not exist")
        elif not self.path.is_file():
            raise IsADirectoryError(f"{self.path} is not a file")

        # remember additional keyword arguments
        self.kwargs = corpus_kwargs

    def __repr__(self):
        return f"{self.__class__.__name__}({self.path})"

    def files(self):
        return [self.path]

    def data(self, *args, **kwargs):
        kwargs = {**self.kwargs, **kwargs}
        file_reader = kwargs.pop('file_reader', None)
        if file_reader is None:
            return self.path
        else:
            return file_reader(self.path, *args, **kwargs)

class JSONFileCorpus(SingleFileCorpus):
    """A corpus consisting of a single JSON file."""

    def data(self, *args, **kwargs):
        kwargs = {**self.kwargs, **kwargs}
        # *args are ignored but catch arguments for convenience
        with open(self.path, 'r') as f:
            return json.load(f, **kwargs)

class JSONLinesFileCorpus(SingleFileCorpus):
    """A corpus consisting of a single JSONL file."""

    def data(self, *args, **kwargs):
        kwargs = {**self.kwargs, **kwargs}
        with open(self.path, 'r') as f:
            return [json.loads(line) for line in f]

class CSVFileCorpus(SingleFileCorpus):
    """A corpus consisting of a single TSV/CSV file."""

    def __init__(self, *args, sep=',', **kwargs):
        # initialize single file corpus normally
        super().__init__(*args, **kwargs)

        # read the separator (this should become unnecessary when switching to JSON/YAML configs)
        if sep[0] == '"' or sep[0] == "'":
            sep = ast.literal_eval(sep)
        # remember the separator
        self.sep = sep

    def data(self, *args, **kwargs):
        kwargs = {**self.kwargs, "sep": self.sep, **kwargs}
        return pandas.read_csv(self.path, **kwargs)
