from enkan.mySlideshow.ScopeStack import ScopeStack, ScopeStackEntry


def test_scope_stack_push_peek_pop_round_trip():
    stack = ScopeStack[int](2)
    entry = ScopeStackEntry(path="root\\child", image_paths=["a.jpg"], scope_state=7)

    assert stack.push(entry) is True
    assert stack.peek() == entry
    assert len(stack) == 1
    assert stack.pop() == entry
    assert stack.pop() is None


def test_scope_stack_peek_supports_depth():
    stack = ScopeStack[int]()
    first = ScopeStackEntry(path="one", image_paths=["1.jpg"], scope_state=1)
    second = ScopeStackEntry(path="two", image_paths=["2.jpg"], scope_state=2)

    stack.push(first)
    stack.push(second)

    assert stack.peek().path == "two"
    assert stack.peek(2).path == "one"
    assert stack.peek(3) is None


def test_scope_stack_respects_max_size():
    stack = ScopeStack[int](1)

    assert stack.push(
        ScopeStackEntry(path="one", image_paths=["1.jpg"], scope_state=1)
    ) is True
    assert stack.push(
        ScopeStackEntry(path="two", image_paths=["2.jpg"], scope_state=2)
    ) is False
    assert stack.is_full() is True
