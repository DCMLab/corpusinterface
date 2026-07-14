#  Copyright (c) 2020 Robert Lieck
import configparser
from pathlib import Path
from warnings import warn
from urllib.request import urlretrieve
from urllib.error import URLError, HTTPError
import shutil

from .util import __DEFAULT__, __ROOT__, __PARENT__, __INHERIT__, __PATH__, DownloadFailedError, \
    CorpusExistsError, CorpusNotFoundError, DuplicateCorpusError, DuplicateDefaultsError, ConfigCycleError

# remember built-in set
python_set = set

# no imports with 'import config *'
# this is primarily to avoid unintentional overwriting of built-in 'set' with config.set
__all__ = []


#############################################
# default paths and functions to get/set them
#############################################

__DEFAULT_default_root_dir__ = Path("~/corpora").expanduser()

__default_root_dir__ = __DEFAULT_default_root_dir__

__DEFAULT_default_config_dir__ = None

__default_config_dir__ = __DEFAULT_default_config_dir__

__default_config_dir_suffix__ = "config"


def get_default_root_dir():
    return __default_root_dir__


def set_default_root_dir(dir):
    global __default_root_dir__
    __default_root_dir__ = Path(dir).expanduser()


def reset_default_root_dir():
    global __default_root_dir__
    __default_root_dir__ = __DEFAULT_default_root_dir__


def get_default_config_dir():
    if __default_config_dir__ is None:
        return __default_root_dir__ / __default_config_dir_suffix__
    else:
        return __default_config_dir__


def set_default_config_dir(dir):
    global __default_config_dir__
    __default_config_dir__ = Path(dir).expanduser()


def reset_default_config_dir():
    global __default_config_dir__
    __default_config_dir__ = __DEFAULT_default_config_dir__


##################
# helper functions
##################

def getbool(value):
    str_value = str(value).lower()
    if str_value in ['1', 'yes', 'true', 'on']:
        return True
    elif str_value in ['0', 'no', 'false', 'off']:
        return False
    else:
        raise ValueError(f"Could not convert value '{value}' to bool.")


def _corpus_to_str(corpus):
    if not isinstance(corpus, str):
        warn(f"corpus '{corpus}' is not a string and will be converted",
             RuntimeWarning)
        corpus = str(corpus)
    return corpus


def _key_to_str(key):
    if not isinstance(key, str):
        warn(f"key '{key}' is not a string and will be converted (note that keys are case insensitive)",
             RuntimeWarning)
        key = str(key)
    key_lower = key.lower()
    if key_lower != key:
        warn(f"keys are case insensitive; key '{key}' is converted to lower-case for consistency '{key_lower}'",
             RuntimeWarning)
    return key_lower


def _value_to_str(value):
    if value is not None and not isinstance(value, str):
        warn(f"value '{value}' is not a string and will be converted",
             RuntimeWarning)
        value = str(value)
    return value


def _get_config_obj():
    return configparser.ConfigParser(allow_no_value=True,
                                     interpolation=configparser.ExtendedInterpolation(),
                                     default_section=__DEFAULT__)


############################################################################
# The configuration data is stored in and accessed via a ConfigParser object
############################################################################

__config__ = _get_config_obj()


##############################################################
# functions for initialising config and adding new information
##############################################################

def init_config(*args, default=None, home=None, local=None):
    # default config that is part of the package (located on the same level as this file)
    default_file = Path(__file__).parents[0] / 'default_config.ini'
    if default:
        load_config(default_file)
    elif default is None:
        __config__.read(default_file)

    # config files in default config directory
    if home or home is None:
        found_config = False
        for path in get_default_config_dir().glob('*.ini'):
            __config__.read(path)
            found_config = True
        if home and not found_config:
            raise FileNotFoundError(f"Could not find any config files (*.ini) in directory "
                                    f"'{get_default_config_dir()}'")

    # config file in current working directory
    local_file = 'corpora.ini'
    if local:
        load_config(local_file)
    elif local is None:
        __config__.read(local_file)

    # load explicitly provided files
    for file in args:
        load_config(file)


def reset_config(*args, **kwargs):
    clear_config(clear_default=True)
    init_config(*args, **kwargs)


def load_config(file, merge_duplicates=False, merge_defaults=False):
    # if we cannot just merge everything
    if not merge_duplicates or not merge_defaults:
        # first load into separate config
        tmp_config = _get_config_obj()
        with open(file) as f:
            tmp_config.read_file(f)
        # check for duplicate sections/corpora
        if not merge_duplicates:
            # get sections as sets
            old_sections = python_set(__config__.sections())
            new_sections = python_set(tmp_config.sections())
            # check whether they are disjoints and raise if they are not
            if not old_sections.isdisjoint(new_sections):
                raise DuplicateCorpusError(f"Config file '{file}' contains corpora that are already present "
                                           f"({old_sections.intersection(new_sections)}). "
                                           f"Use merge_duplicates=True to merge them.")
        # check for non-empty defaults on both configs
        if not merge_defaults and __config__.defaults() and tmp_config.defaults():
            raise DuplicateDefaultsError(f"Existing config and config from file '{file}' both contain non-empty "
                                         f"defaults. Use merge_defaults=True to merge them.")
    with open(file) as f:
        __config__.read_file(f)


def download_config(url, name, dir=None, load=False, **kwargs):
    # download to tmp file
    try:
        tmp_file_name, _ = urlretrieve(url=url)
    except (HTTPError, URLError) as e:
        raise DownloadFailedError(f"Opening url '{url}' failed: {e}")
    # get directory to save file
    if dir is None:
        dir = get_default_config_dir()
    else:
        dir = Path(dir)
    # get full path to target file
    file_path = dir / name
    # check if file already exists
    if file_path.exists():
        raise FileExistsError(f"Cannot save config file to '{file_path}', file already exists.")
    if not dir.exists():
        dir.mkdir(parents=True)
    # copy file
    shutil.copyfile(tmp_file_name, file_path)
    # load file
    if load:
        load_config(file_path, **kwargs)


def set_key_value(corpus, key, value):
    corpus = _corpus_to_str(corpus)
    if not corpus in __config__:
        raise CorpusNotFoundError(f"Corpus '{corpus}' not found in config")
    else:
        __config__[corpus][_key_to_str(key)] = _value_to_str(value)


def set_values(corpus, **kwargs):
    for key, value in kwargs.items():
        set_key_value(corpus, key=key, value=value)


def set(*args, **kwargs):
    warn("config.set() is deprecated. Use config.set_values() instead.", DeprecationWarning)
    return set_values(*args, **kwargs)


def unset_value(corpus, key, not_exists_ok=False):
    if not corpus in __config__:
        raise CorpusNotFoundError(f"Corpus '{corpus}' not found in config")
    if not_exists_ok:
        __config__[corpus].pop(key, None)
    else:
        __config__[corpus].pop(key)


def add_corpus(corpus, exists_ok=False, **kwargs):
    corpus = _corpus_to_str(corpus)
    if corpus in __config__:
        if not exists_ok:
            raise CorpusExistsError(f"Corpus '{corpus}' already exists in config. Use set() to modify values.")
    else:
        # add empty corpus
        __config__[corpus] = {}
    # add key-value pairs
    set_values(corpus, **kwargs)


def set_default_key_value(key, value=None):
    set_key_value(__DEFAULT__, key=key, value=value)


def set_default(**kwargs):
    set_values(__DEFAULT__, **kwargs)


################################################
# functions for deleting information from config
################################################

def delete_corpus(corpus, not_exists_ok=False):
    corpus = _corpus_to_str(corpus)
    if corpus not in __config__:
        if not_exists_ok:
            return
        else:
            raise CorpusNotFoundError(f"Corpus '{corpus}' not found in config")
    assert __config__.remove_section(section=corpus)


def clear_config(clear_default=False):
    for sec in __config__.sections():
        assert __config__.remove_section(section=sec)
    if clear_default:
        __config__[__DEFAULT__] = {}


##################################################
# functions for retrieving information from config
##################################################

def _get(corpus, key, raw=False, _first_call=True):
    """
    Wrapper around raw config values that handles special parameters, such as __ROOT__ and __PATH__.
    """
    if _first_call:
        _get.visited_parents = []
    if not raw:
        # unless raw values are requested, return processed versions of root and path
        if key == __ROOT__:
            # for sub-corpora the root is replaced by the parent's path
            parent = _get(corpus, __PARENT__, _first_call=False)
            if parent in _get.visited_parents:
                raise ConfigCycleError(f"Cycle in parent-child relation when revisiting '{parent}' "
                                       f"(visited before: {_get.visited_parents})")
            else:
                _get.visited_parents.append(parent)
            if parent is not None:
                root = _get(parent, __PATH__, _first_call=False)
            else:
                root = __config__[_corpus_to_str(corpus)][__ROOT__]
                if root is None:
                    root = get_default_root_dir()
                else:
                    root = Path(root).expanduser()
            if not root.is_absolute():
                warn(f"Root for corpus '{corpus}' is a relative path ('{root}'), "
                     f"which is interpreted relative to the current "
                     f"working directory ('{Path.cwd()}')", RuntimeWarning)
            return root
        elif key == __PATH__:
            # get raw value
            path = __config__[_corpus_to_str(corpus)][__PATH__]
            # if not specified, default to corpus name
            if path is None:
                path = corpus
            # convert to path
            path = Path(path).expanduser()
            # absolut paths overwrite root; relative paths are appended
            if path.is_absolute():
                return path
            else:
                return _get(corpus, __ROOT__, _first_call=False) / path
    # default (and if raw is requested): return values directly from config
    return __config__[_corpus_to_str(corpus)][_key_to_str(key)]

_get.visited_parents = []


def corpora():
    yield from __config__.sections()


def corpus_params(corpus, raw=False):
    return _corpus_params(corpus, raw=raw, _first_call=True)


def _corpus_params(corpus, raw=False, _first_call=False):
    # reset on first call
    if _first_call:
        _corpus_params.visited_parents = []
    # map value to string if necessary
    corpus = _corpus_to_str(corpus)
    # check if corpus exists
    if corpus not in __config__:
        raise CorpusNotFoundError(f"Corpus '{corpus}' not found in config")
    # get parameters
    params = {key: _get(corpus, key, raw=raw) for key in __config__[corpus]}
    # populate with parent parameters if requested
    if getbool(params.get(__INHERIT__, False)):
        # get parent
        parent = _get(corpus, __PARENT__)
        # check for cycles
        if parent in _corpus_params.visited_parents:
            raise ConfigCycleError(f"Cycle in parent-child relation when revisiting '{parent}' "
                                   f"(visited before: {_corpus_params.visited_parents})")
        else:
            _corpus_params.visited_parents.append(parent)
        # merge with parent parameters (child overwrites parent, except for __INHERIT__)
        if parent is not None:
            parent_params = _corpus_params(parent, raw=raw)
            return {**parent_params, **params, __INHERIT__: parent_params.get(__INHERIT__, False)}
    return params

_corpus_params.visited_parents = []


def get(corpus, key, raw=False):
    # get all parameters to account for inheritance
    return corpus_params(corpus, raw=raw)[_key_to_str(key)]


def summary(corpus=None, raw=False):
    if corpus is None:
        # without specific corpus summarise all corpora
        return "\n\n".join(summary(corpus, raw=raw) for corpus in [__DEFAULT__] + list(corpora()))
    else:
        # summarise corpus by providing all parameters
        corpus = _corpus_to_str(corpus)
        s = f"[{corpus}]"
        for key, val in corpus_params(corpus, raw=raw).items():
            s += f"\n    {key}: {val}"
        return s


####################################
# Initialise config on module import
####################################
init_config()
