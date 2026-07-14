#  Copyright (c) 2020 Robert Lieck

################
# some constants
################

# the default section
__DEFAULT__ = "DEFAULT"

# standard parameters and keys
__INFO__ = "info"
__ROOT__ = "root"
__PATH__ = "path"
__FILE__ = "file"
__PARENT__ = "parent"
__INHERIT__ = "inherit"
__ACCESS__ = "access"
__URL__ = "url"
__DOWNLOAD__ = "download"
__DOWNLOAD_ARGS__ = "download_args"
__LOADER__ = "loader"


###################
# custom exceptions
###################

class CorpusNotFoundError(KeyError):
    pass


class CorpusExistsError(Exception):
    pass


class DownloadFailedError(Exception):
    pass


class LoadingFailedError(Exception):
    pass


class DuplicateCorpusError(Exception):
    pass


class DuplicateDefaultsError(Exception):
    pass


class ConfigCycleError(Exception):
    pass
