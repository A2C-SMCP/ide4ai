# filename: test_dispose.py
# @Time    : 2024/4/19 10:30
# @Author  : JQQ
# @Email   : jqq1716@gmail.com
# @Software: PyCharm
from unittest.mock import MagicMock

import pytest
from tfrobot.drive.tool.ides.environment.workspace.common import dispose
from tfrobot.drive.tool.ides.environment.workspace.common.dispose import (
    Disposable,
    DisposableMap,
    DisposableStore,
    DisposableTracker,
    MutableDisposable,
    combined_disposable,
    mark_as_singleton,
    set_disposable_tracker,
    to_disposable,
)


@pytest.fixture
def tracker():
    original_value = dispose.TRACK_DISPOSABLES
    dispose.TRACK_DISPOSABLES = True
    tracker = dispose.DisposableTracker()
    dispose.set_disposable_tracker(tracker)
    yield tracker
    dispose.set_disposable_tracker(None)
    dispose.TRACK_DISPOSABLES = original_value


def test_tracking_disposables(tracker):
    disposable = dispose.Disposable()
    tracker.track_disposable(disposable)
    assert getattr(disposable, tracker.__is_disposable_tracked__, False)


def test_mark_as_disposed(tracker):
    disposable = dispose.Disposable()
    tracker.mark_as_disposed(disposable)
    assert getattr(disposable, tracker.__is_disposable_tracked__, False)


def test_disposable_basic():
    disposable = Disposable()
    assert not disposable._store.is_disposed
    disposable.dispose()
    assert disposable._store.is_disposed


def test_disposable_store_add_and_dispose():
    store = DisposableStore()
    disposable = Disposable()
    store.add(disposable)
    assert disposable in store._to_dispose
    store.dispose()
    assert store.is_disposed
    assert not store._to_dispose


def test_disposable_store_double_dispose():
    store = DisposableStore()
    store.dispose()
    # 第二次调用dispose，应无任何作用但也不应该引发错误
    store.dispose()
    assert store.is_disposed


def test_mutable_disposable():
    mutable = MutableDisposable()
    assert mutable.value is None
    new_disposable = Disposable()
    mutable.value = new_disposable
    assert mutable.value == new_disposable
    mutable.dispose()
    assert mutable._is_disposed
    assert mutable.value is None


def test_disposable_map_lifecycle(capfd):
    dmap = DisposableMap()
    key, value = "key1", Disposable()
    dmap.set(key, value)
    assert dmap.get(key) == value
    dmap.dispose()
    assert dmap._is_disposed
    # with pytest.raises(KeyError):
    #     dmap.get(key)  # 由于已dispose，key应被删除，但因为在调用key的时候使用的是 .get 方法，所以不会抛出KeyError，但返回应该是None
    assert dmap.get(key) is None
    dmap.set(key, value)
    out, _ = capfd.readouterr()
    assert "already been disposed" in out


def test_exception_handling_in_dispose():
    class FaultyDisposable(Disposable):
        def dispose(self):
            raise Exception("Intentional failure")

    faulty = FaultyDisposable()
    with pytest.raises(Exception) as exc_info:
        faulty.dispose()
    assert str(exc_info.value) == "Intentional failure"


def test_add_disposed_store(capfd):
    store = dispose.DisposableStore()
    store.dispose()
    disposable = dispose.Disposable()
    store.add(disposable)
    out, err = capfd.readouterr()
    assert "already been disposed" in out


def test_delete_and_leak_nonexistent(tracker):
    store = dispose.DisposableStore()
    disposable = dispose.Disposable()
    # 测试尝试删除不存在于集合中的对象
    store.delete_and_leak(disposable)  # 应该不抛出错误
    store.add(disposable)
    assert disposable in store._to_dispose
    store.delete_and_leak(disposable)
    assert disposable not in store._to_dispose


def test_disposable_register():
    disposable = dispose.Disposable()
    other_disposable = dispose.Disposable()
    with pytest.raises(Exception) as exc_info:
        disposable.register(disposable)
    assert "Cannot register a disposable on itself" in str(exc_info.value)
    disposable.register(other_disposable)
    assert other_disposable in disposable._store._to_dispose


def test_ref_counted_disposable(tracker):
    disposable = dispose.Disposable()
    ref = dispose.RefCountedDisposable(disposable)
    ref.acquire()
    ref.release()
    ref.release()  # 这应该会调用disposable.dispose()
    assert disposable._store.is_disposed


def test_mutable_disposable_value_change(tracker):
    mutable = dispose.MutableDisposable()
    disposable1 = dispose.Disposable()
    disposable2 = dispose.Disposable()
    mutable.value = disposable1
    mutable.value = disposable2
    # 确保disposable1被废弃
    assert disposable1._store.is_disposed
    assert mutable.value is disposable2


def test_clear_mutable_disposable(tracker):
    mutable = dispose.MutableDisposable()
    disposable = dispose.Disposable()
    mutable.value = disposable
    mutable.clear()
    assert mutable.value is None
    assert disposable._store.is_disposed


def test_dispose_iterable_with_errors(tracker):
    class FaultyDisposable(dispose.Disposable):
        def dispose(self):
            raise Exception("Fault during dispose")

    faulty = FaultyDisposable()
    disposables = [dispose.Disposable(), faulty]
    with pytest.raises(Exception) as exc_info:
        dispose.dispose(disposables)
    assert "Fault during dispose" in str(exc_info.value)
    single_disposable = MagicMock(spec=Disposable)
    dispose.dispose(single_disposable)  # type: ignore
    single_disposable.dispose.assert_called_once()


def test_track_disposables_enabled():
    dispose.TRACK_DISPOSABLES = True
    dispose.set_disposable_tracker(dispose.DisposableTracker())
    assert dispose.disposable_tracker is not None
    dispose.TRACK_DISPOSABLES = False  # 重置为默认值


def test_mark_as_singleton(tracker):
    disposable = dispose.Disposable()
    tracker.mark_as_singleton(disposable)
    # 检查是否设置了某个属性或者状态，取决于mark_as_singleton具体应有的效果


def test_add_non_disposable():
    store = dispose.DisposableStore()
    non_disposable = object()  # 非 DisposableProtocol 对象
    result = store.add(non_disposable)  # noqa
    assert result == non_disposable  # 应返回输入的对象，因为它不是 disposable


def test_add_self():
    store = dispose.DisposableStore()
    with pytest.raises(Exception) as exc_info:
        store.add(store)
    assert "Cannot register a disposable on itself" in str(exc_info.value)


def test_disposed_store_adds_disposable(capfd):
    store = dispose.DisposableStore()
    store.dispose()
    disposable = dispose.Disposable()
    store.add(disposable)
    out, _ = capfd.readouterr()
    assert "already been disposed" in out


def test_delete_and_leak_nonexistent_item():
    store = dispose.DisposableStore()
    disposable = dispose.Disposable()
    # 测试尝试删除不存在于集合中的对象
    store.delete_and_leak(disposable)  # 应该无操作，也不抛出错误


def test_mutable_disposable_value_set_and_clear():
    mutable = dispose.MutableDisposable()
    disposable1 = dispose.Disposable()
    mutable.value = disposable1
    assert mutable.value == disposable1
    mutable.clear()
    assert mutable.value is None


def test_ref_counted_disposable_again():
    disposable = dispose.Disposable()
    ref_counted = dispose.RefCountedDisposable(disposable)
    assert ref_counted._counter == 1
    ref_counted.acquire()
    assert ref_counted._counter == 2
    ref_counted.release()
    assert ref_counted._counter == 1
    ref_counted.release()  # 这应该会触发dispose
    assert disposable._store.is_disposed


def test_dispose_with_multiple_errors():
    disposable1 = Disposable()
    disposable2 = Disposable()
    disposable1.dispose = MagicMock(side_effect=Exception("Error 1"))
    disposable2.dispose = MagicMock(side_effect=Exception("Error 2"))

    with pytest.raises(Exception) as exc_info:
        dispose.dispose([disposable1, disposable2])

    assert "Encountered errors" in str(exc_info.value)


def test_to_disposable():
    was_called = False

    def fake_fn():
        nonlocal was_called
        was_called = True

    disposable = to_disposable(fake_fn)
    disposable.dispose()
    assert was_called is True


def test_mark_as_disposed_global():
    tracker = DisposableTracker()
    set_disposable_tracker(tracker)
    disposable = Disposable()
    disposable.dispose()
    # Verify that `__is_disposable_tracked__` is set to True
    assert getattr(disposable, "__is_disposable_tracked__", False) is True


def test_overwrite_skip_dispose():
    dmap = DisposableMap()
    key, value = "key1", MagicMock(spec=Disposable)
    dmap.set(key, value)
    assert dmap.get(key) == value
    dmap.dispose()
    assert dmap._is_disposed
    # with pytest.raises(KeyError):
    #     dmap.get(key)  # 由于已dispose，key应被删除，但因为在调用key的时候使用的是 .get 方法，所以不会抛出KeyError，但返回应该是None
    assert dmap.get(key) is None
    new_value = MagicMock(spec=Disposable)
    dmap.set(key, new_value)
    another_value = MagicMock(spec=Disposable)
    dmap.set(key, another_value, skip_dispose_on_overwrite=False)
    new_value.dispose.assert_called_once()
    assert dmap.get(key) is another_value


def test_disposable_map_delete_and_dispose():
    disposable_map = DisposableMap()
    disposable = Disposable()
    disposable_map.set("key1", disposable)
    disposable_map.delete_and_dispose("key1")
    # After deletion and dispose, the key should not exist and the disposable should be disposed
    assert "key1" not in disposable_map._store
    assert disposable._store._is_disposed is True


def test_combined_disposable():
    d1 = Disposable()
    d2 = Disposable()
    combined = combined_disposable(d1, d2)
    assert not d1._store._is_disposed
    assert not d2._store._is_disposed
    combined.dispose()
    # After disposing the combined, both should be disposed
    assert d1._store._is_disposed
    assert d2._store._is_disposed


def test_global_mark_as_singleton(tracker):
    tracker.mark_as_singleton = MagicMock()
    d1 = MagicMock(spec=Disposable)
    mark_as_singleton(d1)
    tracker.mark_as_singleton.assert_called_once()
