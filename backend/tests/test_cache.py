from app.cache import InMemoryJsonCache, stable_cache_key


def test_stable_cache_key_is_order_independent() -> None:
    first = stable_cache_key("answer", {"question": "What?", "top_k": 5})
    second = stable_cache_key("answer", {"top_k": 5, "question": "What?"})

    assert first == second
    assert first.startswith("answer:")


def test_in_memory_cache_stores_json_and_deletes_prefix() -> None:
    cache = InMemoryJsonCache()
    cache.set_json("answer:1", {"value": 1}, ttl_seconds=60)
    cache.set_json("embedding:1", [0.1, 0.2], ttl_seconds=60)

    assert cache.get_json("answer:1") == {"value": 1}
    assert cache.delete_prefix("answer:") == 1
    assert cache.get_json("answer:1") is None
    assert cache.get_json("embedding:1") == [0.1, 0.2]
