from typing import Any, Callable, TypeVar, overload

_F = TypeVar("_F", bound=Callable[..., Any])


class Node:
    nodeid: str


class FixtureRequest:
    node: Node


class MarkDecorator:
    @overload
    def __call__(self, function: _F, /) -> _F: ...
    @overload
    def __call__(self, *args: Any, **kwargs: Any) -> MarkDecorator: ...


class MarkGenerator:
    smoke: MarkDecorator
    full: MarkDecorator

    def __getattr__(self, name: str) -> MarkDecorator: ...


mark: MarkGenerator


@overload
def fixture(function: _F, /) -> _F: ...
@overload
def fixture(
    *,
    scope: str | None = ...,
    params: Any = ...,
    autouse: bool = ...,
    ids: Any = ...,
    name: str | None = ...,
) -> Callable[[_F], _F]: ...
