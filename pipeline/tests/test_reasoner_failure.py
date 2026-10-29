"""
Fault injection: the reasoner is unavailable (Revision 6, defect D18).

The pipeline must fail loudly with SKLReasonerError and emit neither a plan
nor a programme; it must never fall back to defaults. Three injections: no
runnable Java, a Java older than the bundled Pellet jars require, and a
class-version failure raised by Pellet itself.
"""
import glob
import os
import subprocess
import sys

import pytest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, 'src'))

import owlready2  # noqa: E402
import skl_repository  # noqa: E402
from skl_repository import SKLRepository, SKLReasonerError  # noqa: E402


def test_required_java_is_read_from_bundled_pellet_jars():
    # owlready2 0.51: jena-arq-fixed2.10.0.jar carries class-file version 69.
    assert SKLRepository.required_java_major() == 25


def test_reasoner_without_runnable_java_fails_loudly(monkeypatch):
    monkeypatch.setattr(SKLRepository, '_java_major_version', staticmethod(lambda exe: None))
    with pytest.raises(SKLReasonerError, match='No Java 25'):
        SKLRepository(java_exe=r'C:\nonexistent\bin\java.exe')


def test_reasoner_with_too_old_java_fails_loudly(monkeypatch):
    # A Java 21 was accepted before Revision 6 and then failed inside Pellet.
    monkeypatch.setattr(SKLRepository, '_java_major_version', staticmethod(lambda exe: 21))
    with pytest.raises(SKLReasonerError, match='No Java 25'):
        SKLRepository()


def test_pellet_class_version_failure_fails_loudly(monkeypatch):
    repo = SKLRepository()

    def broken_pellet(*args, **kwargs):
        raise owlready2.OwlReadyJavaError(
            'java.lang.UnsupportedClassVersionError: class file version 69.0; this Java recognises up to 65.0')

    monkeypatch.setattr(skl_repository, 'sync_reasoner_pellet', broken_pellet)
    with pytest.raises(SKLReasonerError, match='UnsupportedClassVersionError'):
        repo.reason()
    assert repo.reasoning_status == 'java_error'


INJECT = (
    "import sys, runpy; sys.path.insert(0, 'src'); import skl_repository; "
    "skl_repository.SKLRepository._java_major_version = staticmethod(lambda exe: None); "
    "sys.argv = ['main.py', '--output-dir', sys.argv[1]]; runpy.run_path('main.py', run_name='__main__')"
)


def test_pipeline_without_reasoner_emits_no_plan_or_programme(tmp_path):
    out = tmp_path / 'no_reasoner'
    out.mkdir()
    env = dict(os.environ, PYTHONIOENCODING='utf-8')
    r = subprocess.run([sys.executable, '-c', INJECT, str(out)], cwd=BASE_DIR, env=env,
                       capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=600)
    assert r.returncode != 0
    assert 'SKLReasonerError' in r.stderr
    emitted = {os.path.basename(p) for p in glob.glob(str(out / '*'))}
    assert 'manufacturing_plan.json' not in emitted
    assert not [p for p in emitted if p.endswith('.nc')]
    assert 'expert_validation_requests.json' not in emitted
