#  Copyright (c) 2020 Robert Lieck
from pathlib import Path
from urllib.request import urlretrieve
from urllib.error import URLError, HTTPError
import tarfile
import zipfile
import gzip, bz2, lzma
import shutil

import git
from tqdm.auto import tqdm

from . import config
from .corpora import FileCorpus, ZipFileCorpus, TarFileCorpus, SingleFileCorpus, JSONFileCorpus, JSONLinesFileCorpus, CSVFileCorpus
from .util import __DOWNLOAD__, __DOWNLOAD_ARGS__, __ACCESS__, __LOADER__, __URL__, __FILE__, \
    CorpusNotFoundError, DownloadFailedError, LoadingFailedError


# mappings of string values provided in corpus config or as keywords in load()
_keyword_mappings = {
    __LOADER__: {
        "FileCorpus": FileCorpus,
        "ZipFileCorpus": ZipFileCorpus,
        "TarFileCorpus": TarFileCorpus,
        "SingleFileCorpus": SingleFileCorpus,
        "JSONFileCorpus": JSONFileCorpus,
        "JSONLinesFileCorpus": JSONLinesFileCorpus,
        "CSVFileCorpus": CSVFileCorpus,
    }
}

def add_keyword_mapping(keyword, value, mapping, overwrite=False):
    """
    Add a keyword mapping to be used in load(). All keyword mappings are stored in _keyword_mappings.

    Keywords specified in the config or passed explicitly to load() can be mapped to arbitrary values. For instance,
    if you have a custom file reader function that you want to use with FileCorpus, you can add a mapping like this:

    Example:
        >>> def my_custom_reader(**kwargs):
        ...     # your custom loading logic here
        ...     pass
        >>> add_keyword_mapping("file_reader", "my custom reader", my_custom_reader)
        # Now you can use it in load():
        >>> load(..., file_reader="my custom reader")
        # Or in your config INI, you can add a line ``file_reader: my custom reader``.

    The load() function automatically populates keyword arguments from config and tries to remap them if a matching
    keyword mapping is found. This is passed to the loader function. If FileCorpus is used as loader function,
    it remembers it and uses it when calling the data() iterator. By the way, loader functions are also defined via
    keyword mappings.
    """
    _keyword_mappings.setdefault(keyword, {})
    if not overwrite and value in _keyword_mappings[keyword]:
        raise ValueError(f"Keyword '{keyword}' already has value '{value}' mapped to '{_keyword_mappings[keyword][value]}'")
    else:
        _keyword_mappings[keyword][value] = mapping


def remove_keyword_mapping(keyword, value):
    try:
        _keyword_mappings[keyword].pop(value)
    except KeyError as e:
        raise KeyError(f"Keyword '{keyword}' does not have value '{value}' mapped to anything.") from e
    if not _keyword_mappings[keyword]:
        _keyword_mappings.pop(keyword)


def populate_kwargs(corpus, kwargs_dict):
    # populate keyword arguments from config
    if corpus is not None:
        kwargs = {**config.corpus_params(corpus), **kwargs_dict}
    else:
        kwargs = kwargs_dict.copy()
    # remap predefined keywords
    for k, v in kwargs.items():
        if isinstance(v, str):
            try:
                kwargs[k] = _keyword_mappings[k][v]
            except KeyError:
                pass  # ignore unknown keywords
    return kwargs


def remove(corpus, silent=False, not_exists_ok=False, not_dir_ok=False, **kwargs):
    # populate keyword arguments
    kwargs = populate_kwargs(corpus, kwargs)
    # get path to remove
    path = Path(kwargs[config.__PATH__])
    # check path
    if path.exists():
        if not path.is_dir() and not not_dir_ok:
            raise NotADirectoryError(f"Path {path} for corpus '{corpus}' is not a directory.")
    else:
        if not not_exists_ok:
            raise FileNotFoundError(f"Path {path} for corpus '{corpus}' does not exist.")
        else:
            return
    # get confirmation
    if not silent:
        while True:
            rm = input(f"Remove corpus '{corpus}' ({path}) [y/N]: ").strip().lower()
            if rm in ['y', 'yes']:
                rm = True
                break
            elif rm in ['', 'n', 'no']:
                rm = False
                break
    else:
        rm = True
    # remove
    if rm:
        shutil.rmtree(path)
    else:
        print(f"Canceled. Corpus '{corpus}' ({path}) not removed.")


def load(corpus=None, **kwargs):
    """
    Load a corpus.
    :param corpus: Name of the corpus to load or None to only use given keyword arguments.
    :param kwargs: Keyword arguments that are populated from config; specifying parameters as keyword arguments take
    precedence over the values from config.
    :return: output of loader
    """
    # populate keyword arguments from config
    populated_kwargs = populate_kwargs(corpus, kwargs)
    # check if corpus exists
    path = Path(populated_kwargs[config.__PATH__])
    if path.exists():
        if __LOADER__ in populated_kwargs:
            # extract loader from kwargs
            loader = populated_kwargs[__LOADER__]
            # if string was provided, lookup loader function
            if isinstance(loader, str):
                raise LoadingFailedError(f"Unknown {__LOADER__} '{loader}'.")
            # make sure loader is callable
            if not callable(loader):
                raise LoadingFailedError(f"{__LOADER__} '{loader}' is not callable.")
            # call loader
            return loader(**populated_kwargs)
        else:
            raise LoadingFailedError("No loader specified.")
    else:
        # if it does not exist, try downloading (if requested) and then retry
        if config.getbool(populated_kwargs.get(__DOWNLOAD__, False)):
            # download using original (unpopulated) kwargs
            download(corpus, **kwargs)
            # prevent second download attempt in reload
            kwargs[__DOWNLOAD__] = False
                        # reload
            return load(corpus, **kwargs)
        else:
            raise CorpusNotFoundError(f"Corpus '{corpus}' at path '{path}' does not exist "
                                      f"(specify {__DOWNLOAD__}=True to try downloading).")


def create_download_path(corpus, kwargs):
    path = Path(kwargs[config.__PATH__])
    if path.exists():
        # directory is not empty
        if path.is_file() or list(path.iterdir()):
            raise DownloadFailedError(f"Cannot download corpus '{corpus}': "
                                      f"target path {path} exists and is non-empty.")
    else:
        path.mkdir(parents=True)
    return path

__KNOWN_ACCESS_METHODS__ = [
    'git',
    'zip',
    'tar.gz',
    'file',
    'gz',
    'xz',
    'bz2',
]

def download(corpus, **kwargs):
    if corpus is not None and config.get(corpus, config.__PARENT__) is not None:
        # for sub-corpora delegate downloading to parent
        download(config.get(corpus, config.__PARENT__), **kwargs)
    else:
        # populate keyword arguments from config
        kwargs = populate_kwargs(corpus, kwargs)
        # get access method
        access = kwargs[__ACCESS__]
        # check if method is known
        if access in __KNOWN_ACCESS_METHODS__ or callable(access):
            path = create_download_path(corpus, kwargs)
        else:
            raise DownloadFailedError(f"Unknown access method '{access}'")

        # use known access method or provided callable
        try:
            if access == 'git':
                # clone directly into the target directory
                url = kwargs[__URL__]
                try:
                    # split __DOWNLOAD_ARGS__ on commas into separate arguments
                    download_args = [a.strip() for a in kwargs[__DOWNLOAD_ARGS__].split(',')]
                except KeyError:
                    download_args = []
                # clone with progress bar
                with tqdm(desc=f"Cloning {kwargs[__URL__]}", unit="B", unit_scale=True) as pbar:
                    # derive from right base
                    class ProgressPrinter(git.RemoteProgress):
                        def update(self, op_code, cur_count, max_count=None, message=''):
                            if max_count:
                                pbar.total = max_count
                            pbar.n = cur_count
                            pbar.refresh()
                    # clone
                    git.Repo.clone_from(url=url, to_path=path, progress=ProgressPrinter(), multi_options=download_args)
            elif access in ['zip', 'tar.gz', 'file', 'gz', 'xz', 'bz2']:
                # download to temporary file
                url = kwargs[__URL__]
                # callback for progress bar
                pbar = None
                def reporthook(block_num, block_size, total_size):
                    nonlocal pbar
                    if pbar is None:
                        pbar = tqdm(
                            total=total_size if total_size > 0 else None,
                            unit="B",
                            unit_scale=True,
                            unit_divisor=1024,
                            desc=url,
                        )
                    downloaded = block_num * block_size
                    pbar.update(downloaded - pbar.n)
                try:
                    # urlopen(url)
                    tmp_file_name, _ = urlretrieve(url=url, reporthook=reporthook) # TODO: urlretrieve may be deprecated
                except (HTTPError, URLError) as e:
                    raise DownloadFailedError(f"Opening url '{url}' failed: {e}") from e
                finally:
                    if pbar is not None:
                        pbar.close()
                # open with custom method
                if access == 'tar.gz':
                    with tarfile.open(tmp_file_name, "r:gz") as tmp_file:
                        tmp_file.extractall(path)
                elif access == 'zip':
                    with zipfile.ZipFile(tmp_file_name) as tmp_file:
                        tmp_file.extractall(path)
                elif access == 'file':
                    target = path / kwargs[__FILE__]
                    shutil.copy(tmp_file_name, target)
                elif access == 'gz':
                    target = path / kwargs[__FILE__]
                    with gzip.open(tmp_file_name, 'rb') as f_in:
                        with open(target, 'wb') as f_out:
                            shutil.copyfileobj(f_in, f_out)
                elif access == 'xz':
                    target = path / kwargs[__FILE__]
                    with lzma.open(tmp_file_name, 'rb') as f_in:
                        with open(target, 'wb') as f_out:
                            shutil.copyfileobj(f_in, f_out)
                elif access == 'bz2':
                    target = path / kwargs[__FILE__]
                    with bz2.open(tmp_file_name, 'rb') as f_in:
                        with open(target, 'wb') as f_out:
                            shutil.copyfileobj(f_in, f_out)
            elif callable(access):
                # access is a callable
                create_download_path(corpus, kwargs)
                return access(corpus, **kwargs)
        except:
            # clean up the target directory
            shutil.rmtree(path)
            raise
