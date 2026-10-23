import pytest
from autosecretaire.store import Store


def test_persistence_and_rollback(tmp_path):
    s = Store(tmp_path / 'db.sqlite3')
    s.put('client', 'one', {'name': 'Émilie'})
    with pytest.raises(RuntimeError):
        with s.transaction():
            s.put('client', 'two', {'name': 'Deux'})
            raise RuntimeError('rollback')
    assert s.get('client', 'two') is None
    assert Store(tmp_path / 'db.sqlite3').get('client', 'one')['name'] == 'Émilie'
    assert len(s.all('client')) == 1
