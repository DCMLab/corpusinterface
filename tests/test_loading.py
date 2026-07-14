#  Copyright (c) 2020 Robert Lieck
from unittest import TestCase, mock
from pathlib import Path
from io import StringIO
import shutil

from corpusinterface.loading import download, load, remove, CorpusNotFoundError, DownloadFailedError, LoadingFailedError, add_keyword_mapping, remove_keyword_mapping, _keyword_mappings
from corpusinterface import config
from corpusinterface.corpora import FileCorpus
from corpusinterface import util


class Test(TestCase):

    root_path = Path(__file__).parent / "corpora"

    def setUp(self):
        # init and load test corpora into config
        config.reset_config("./tests/test_corpora.ini")
        # set default root to test directory
        config.set_default_key_value(config.__ROOT__, str(self.root_path))

    def tearDown(self):
        # cleanup: remove root directory with downloaded corpora
        if self.root_path.exists():
            shutil.rmtree(self.root_path)

    def test_download(self):
        # custom Exception to check the provided access function was actually executed
        class AccessCheck(Exception):
            pass

        def access(*args, **kwargs):
            raise AccessCheck

        # check different corpora
        for corpus in ["testcorpus-git-http",
                       # "testcorpus-git-ssh",  # does not work in GitHub action
                       "testcorpus-zip",
                       "testcorpus-tar.gz",
                       "testcorpus-file",
                       "testcorpus-gz",
                       "testcorpus-xz",
                       "testcorpus-bz2"]:
            # check with custom access function (raises and leaves directory empty)
            self.assertRaises(AccessCheck, lambda: download(corpus, access=access))
            # check bad access method
            self.assertRaises(DownloadFailedError, lambda: download(corpus, access="bad access method"))
            # download corpus
            download(corpus)
            # assert the directory is there and non-empty
            path = config.get(corpus, util.__PATH__)
            self.assertTrue(list(path.iterdir()))
            # fails because exists
            self.assertRaises(DownloadFailedError, lambda: download(corpus))

        # test failure for bad ULR
        self.assertRaises(DownloadFailedError,
                          lambda: download(None,
                                           access="zip",
                                           path="/tmp/corpus-interface-test-dir-nonsense/",
                                           url="http://some-bad-url-that-skrews-up-the-tests.com/corpus.zip"))

    def test_load_from_child(self):
                # child corpus
        corpus = "testcorpus-zip-child"
        # download
        load(corpus, download=True)
        # assert the directory is there and non-empty
        path = config.get(corpus, util.__PATH__)
        self.assertTrue(list(path.iterdir()))

    def test_load(self):
        corpus = "testcorpus-zip"
        # check load without download (fails)
        self.assertRaises(CorpusNotFoundError, lambda: load(corpus))
        # check load with download; custom loader
        self.assertEqual(1234, load(corpus, download=True, loader=lambda **kwargs: 1234))
        # check load with only keyword arguments
        self.assertEqual(1234, load(path=Path("tests/corpora/testcorpus-zip"), loader=lambda **kwargs: 1234))
        # test with bad loader string
        self.assertRaises(LoadingFailedError, lambda: load(corpus, loader="bad loader"))
        # test with non-callable loader
        self.assertRaises(LoadingFailedError, lambda: load(corpus, loader=1234))
        # test with default loader (FileCorpus)
        c = load(corpus)
        self.assertTrue(str(c).startswith("FileCorpus(") and
                        str(c).endswith("/corpora/testcorpus-zip)") and
                        type(c) == FileCorpus)

    def test_errors(self):
        self.assertRaises(LoadingFailedError, lambda: load(path=Path("tests/FileCorpus")))

    def test_remove(self):
        corpus = "testcorpus-zip"

        # download
        download(corpus)
        path = config.get(corpus, util.__PATH__)
        # assert the directory is there and non-empty
        self.assertTrue(list(path.iterdir()))

        # remove without input cancels
        with mock.patch('builtins.input', return_value=''):
            with mock.patch('sys.stdout', new=StringIO()) as out:
                remove(corpus)
                self.assertTrue(out.getvalue().startswith("Canceled. Corpus '"))
        # assert the directory is there and non-empty
        self.assertTrue(list(path.iterdir()))

        # remove with 'no' input cancels
        with mock.patch('builtins.input', return_value='no'):
            with mock.patch('sys.stdout', new=StringIO()) as out:
                remove(corpus)
                self.assertTrue(out.getvalue().startswith("Canceled. Corpus '"))
        # assert the directory is there and non-empty
        self.assertTrue(list(path.iterdir()))

        # remove with 'yes' input removes
        with mock.patch('builtins.input', return_value='yes'):
            remove(corpus)
        # assert the directory is not there anymore
        self.assertFalse(path.exists())

        # re-download
        download(corpus)
        # assert the directory is there and non-empty
        self.assertTrue(list(path.iterdir()))
        # silent remove succeeds
        remove(corpus, silent=True)
        # assert the directory is not there anymore
        self.assertFalse(path.exists())

        # remove non-existent raises
        self.assertRaises(FileNotFoundError, lambda: remove(corpus, silent=True))
        # which can be ignored
        remove(corpus, not_exists_ok=True, silent=True)

        # path pointing to file raises
        self.assertRaises(NotADirectoryError, lambda: remove(corpus, path='tests/FileCorpus/file_1'))

    def test_keyword_mapping(self):
        original_keyword_mappings = _keyword_mappings.copy()
        add_keyword_mapping("keyword1", "value1", "mapping1")
        self.assertEqual(_keyword_mappings["keyword1"]["value1"], "mapping1")
        self.assertRaises(ValueError, lambda: add_keyword_mapping("keyword1", "value1", "mapping2"))
        remove_keyword_mapping("keyword1", "value1")
        self.assertEqual(_keyword_mappings, original_keyword_mappings)
        self.assertRaises(KeyError, lambda: remove_keyword_mapping("keyword1", "value1"))
