#  Copyright (c) 2020 Robert Lieck
from unittest import TestCase
from pathlib import Path
import json

from corpusinterface.corpora import FileCorpusBase, FileCorpus, ZipFileCorpus, TarFileCorpus, SingleFileCorpus, JSONFileCorpus, JSONLinesFileCorpus, CSVFileCorpus
from corpusinterface.loading import load, add_keyword_mapping, remove_keyword_mapping


class TestFileCorpus(TestCase):

    def test_init(self):
        # 'path' has to be provided
        self.assertRaises(TypeError, lambda: FileCorpus(not_path="tests/DoesNotExist"))
        # positional arguments not allowed
        self.assertRaises(TypeError, lambda: FileCorpus("tests/DoesNotExist"))
        # additional arguments ignored
        self.assertEqual("FileCorpus(tests/FileCorpus)", str(FileCorpus(path="tests/FileCorpus",
                                                                             other_arguments="other")))

    def test_files(self):
        # init with directory that does not exist
        self.assertRaises(FileNotFoundError, lambda: FileCorpus(path="tests/DoesNotExist"))
        # init with file instead of directory
        self.assertRaises(NotADirectoryError, lambda: FileCorpus(path="tests/FileCorpus/file_1"))

        for CorpusClass, extension in zip([FileCorpus, ZipFileCorpus, TarFileCorpus, TarFileCorpus],
                                          ['', '.zip', '.tar', '.tar.gz']):
            path = Path(f"tests/FileCorpus{extension}")

            # init with defaults
            with load(loader=CorpusClass, path=path) as corpus:
                # check it prints as expected
                self.assertEqual(f"{CorpusClass.__name__}(tests/FileCorpus{extension})", str(corpus))
                # check file list
                self.assertEqual(sorted([f"tests/FileCorpus{extension}/file_1",
                                         f"tests/FileCorpus{extension}/file_2",
                                         f"tests/FileCorpus{extension}/sub_dir/file_3",
                                         f"tests/FileCorpus{extension}/sub_dir/file_4"]),
                                 sorted(str(f) for f in corpus.files()))

            # file inclusion regex
            with load(loader=CorpusClass, path=path, file_regex="^file_[23]$") as corpus:
                self.assertEqual(sorted([f"tests/FileCorpus{extension}/file_2",
                                         f"tests/FileCorpus{extension}/sub_dir/file_3"]),
                                 sorted(str(f) for f in corpus.files()))
            # path inclusion regex
            with load(loader=CorpusClass, path=path, path_regex=".+/sub_dir/.+$") as corpus:
                self.assertEqual(sorted([f"tests/FileCorpus{extension}/sub_dir/file_3",
                                         f"tests/FileCorpus{extension}/sub_dir/file_4"]),
                                 sorted(str(f) for f in corpus.files()))
            # file exclusion regex
            with load(loader=CorpusClass, path=path, file_exclude_regex="^file_[23]$") as corpus:
                self.assertEqual(sorted([f"tests/FileCorpus{extension}/file_1",
                                         f"tests/FileCorpus{extension}/sub_dir/file_4"]),
                                 sorted(str(f) for f in corpus.files()))
            # path exclusion regex
            with load(loader=CorpusClass, path=path, path_exclude_regex=".+/sub_dir/.+$") as corpus:
                self.assertEqual(sorted([f"tests/FileCorpus{extension}/file_1",
                                         f"tests/FileCorpus{extension}/file_2"]),
                                 sorted(str(f) for f in corpus.files()))

    def test_data(self):
        file_list = list(sorted(["file_1",
                                 "file_2",
                                 "sub_dir/file_3",
                                 "sub_dir/file_4"]))

        # custom file_reader (gets open file-like object to read from)
        def file_reader(file, prefix, **kwargs):
            with file.open("rt") as f:
                return f"{prefix}: {f.read()}"

        for CorpusClass, extension in zip([FileCorpus, ZipFileCorpus, TarFileCorpus, TarFileCorpus],
                                          ['', '.zip', '.tar', '.tar.gz']):
            path = Path(f"tests/FileCorpus{extension}")

            # without custom file reader (data and files just return PathLike objects)
            with load(loader=CorpusClass, path=path) as corpus:
                self.assertEqual(str(path), str(corpus.metadata()))
                self.assertEqual([f"{path / f} | {Path(f).name}" for f in file_list], sorted(f"{f} | {f.name}" for f in corpus.files()))
                self.assertRaises(TypeError, lambda: list(corpus.data()))  # no file reader defined

            # with custom file_reader
            expected_file_list = [f"{path / f}" for f in file_list]
            expected_data_list = [f"path: {(f.split('/')[-1])} content" for f in file_list]
            # 1. explicitly pass file_reader function
            with load(loader=CorpusClass, path=path, file_reader=file_reader, prefix="path") as corpus:
                self.assertEqual(expected_file_list, sorted(str(f) for f in corpus.files()))
                self.assertEqual(expected_data_list, sorted(f for f in corpus.data()))
                # checking 'return_files'
                self.assertEqual(list(zip(expected_file_list, expected_data_list)), sorted((str(f), d) for f, d in corpus.data(return_files=True)))
                # checking 'lazy_load'
                self.assertEqual(expected_data_list, sorted(f.load() for f in corpus.data(lazy_load=True)))
            # 2. pass undefined string (no mapping performed, raises TypeError)
            with load(loader=CorpusClass, path=path, file_reader="my_file_reader", prefix="path") as corpus:
                self.assertEqual(expected_file_list, sorted(str(f) for f in corpus.files()))
                self.assertRaises(TypeError, lambda: sorted(f for f in corpus.data()))  # FAILS
            # 3. define mapping so lookup works
            add_keyword_mapping(FileCorpusBase.__FILE_READER__, "my_file_reader", file_reader)
            with load(loader=CorpusClass, path=path, file_reader="my_file_reader", prefix="path") as corpus:
                self.assertEqual(expected_file_list, sorted(str(f) for f in corpus.files()))
                self.assertEqual(expected_data_list, sorted(f for f in corpus.data()))
            remove_keyword_mapping(FileCorpusBase.__FILE_READER__, "my_file_reader")

    def test_metadata(self):
        # with defaults, metadata should just return path
        with FileCorpus(path="tests/FileCorpus") as corpus:
            self.assertEqual("tests/FileCorpus", str(corpus.metadata()))

        # custom reader
        def meta_reader(path, prefix, **kwargs):
            return f"{prefix}: {path}"

        with FileCorpus(path="tests/FileCorpus", meta_reader=meta_reader, prefix="path") as corpus:
            self.assertEqual("path: tests/FileCorpus", str(corpus.metadata()))
            self.assertEqual(sorted(["tests/FileCorpus/file_1",
                                     "tests/FileCorpus/file_2",
                                     "tests/FileCorpus/sub_dir/file_3",
                                     "tests/FileCorpus/sub_dir/file_4"]), sorted(str(f) for f in corpus.files()))

class TestSingleFileCorpus(TestCase):

    def test_init(self):
        self.assertRaises(TypeError, lambda: SingleFileCorpus())
        self.assertRaises(TypeError, lambda: SingleFileCorpus(path='tests/SingleFileCorpora'))
        self.assertRaises(FileNotFoundError, lambda: SingleFileCorpus(path='tests/DoesNotExist', file='corpus.json'))
        self.assertRaises(IsADirectoryError, lambda: SingleFileCorpus(path='tests/SingleFileCorpora', file='.'))
        sfc = SingleFileCorpus('tests/SingleFileCorpora', 'corpus.json')
        fn = f"{Path.cwd()}/tests/SingleFileCorpora/corpus.json"
        self.assertEqual(f"SingleFileCorpus({fn})", str(sfc))
        assert [Path(fn)] == sfc.files()
        assert Path(fn) == sfc.data()

    def test_generic(self):
        sf_corpus = SingleFileCorpus('tests/SingleFileCorpora', 'corpus.json')
        def json_reader(fp):
            with open(fp, 'r') as f:
                return json.load(f)
        data = sf_corpus.data(file_reader=json_reader)
        assert [{'name': 'piece1', 'notes': ['c', 'e']}, {'name': 'piece2', 'notes': ['e', 'g']}] == data

    def test_json(self):
        json_corpus = JSONFileCorpus('tests/SingleFileCorpora', 'corpus.json')
        self.assertEqual([{'name': 'piece1', 'notes': ['c', 'e']}, {'name': 'piece2', 'notes': ['e', 'g']}], json_corpus.data())
        
    def test_jsonl(self):
        jsonl_corpus = JSONLinesFileCorpus('tests/SingleFileCorpora', 'corpus.jsonl')
        self.assertEqual([{'name': 'piece1', 'notes': ['c', 'e']}, {'name': 'piece2', 'notes': ['e', 'g']}], jsonl_corpus.data())

    def test_csv(self):
        csv_corpus = CSVFileCorpus('tests/SingleFileCorpora', 'corpus.csv')
        df = csv_corpus.data()
        self.assertEqual(['piece1', 'piece1', 'piece2', 'piece2'], list(df['piece']))
        self.assertEqual(['c', 'e', 'e', 'g'], list(df['note']))

    def test_tsv(self):
        # test loading with pre-set separator
        tsv_corpus = CSVFileCorpus('tests/SingleFileCorpora', 'corpus.tsv', sep='\t')
        df = tsv_corpus.data()
        self.assertEqual(['piece1', 'piece1', 'piece2', 'piece2'], list(df['piece']))
        self.assertEqual(['c', 'e', 'e', 'g'], list(df['note']))

        # test loading with ad-hoc separator
        tsv_corpus_ad_hoc = CSVFileCorpus('tests/SingleFileCorpora', 'corpus.tsv')
        df_ad_hoc = tsv_corpus_ad_hoc.data(sep='\t')
        assert df.equals(df_ad_hoc)

        # test loading with escaped separator
        tsv_corpus_esc = CSVFileCorpus('tests/SingleFileCorpora', 'corpus.tsv', sep='"\t"')
        df_esc = tsv_corpus_esc.data()
        assert df.equals(df_esc)
