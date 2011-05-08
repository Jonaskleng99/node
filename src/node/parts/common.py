import inspect

from odict import odict
from plumber import (
    Part,
    default,
    finalize,
    plumb,
    )
from zope.interface import implements

from node.interfaces import (
    IAdopt,
    IAsAttrAccess,
    INode,
    INodeChildValidate,
    IUnicode,
    IWrap,
    )
from node.utils import AttributeAccess


class Adopt(Part):
    implements(IAdopt)

    @plumb
    def __setitem__(_next, self, key, val):
        # only care about adopting if we have a node
        if not INode.providedBy(val):
            _next(self, key, val)
            return

        # save old __parent__ and __name__ to restore if something goes wrong
        old_name = val.__name__
        old_parent = val.__parent__
        val.__name__ = key
        val.__parent__ = self
        try:
            _next(self, key, val)
        except (AttributeError, KeyError, ValueError):
            # XXX: In what other cases do we want to revert adoption?
            val.__name__ = old_name
            val.__parent__ = old_parent
            raise

    @plumb
    def setdefault(_next, self, key, default=None):
        # We reroute through __getitem__ and __setitem__, skipping _next
        try:
            return self[key]
        except KeyError:
            self[key] = default
            return default


class AsAttrAccess(Part):
    implements(IAsAttrAccess)

    @default
    def as_attribute_access(self):
        return AttributeAccess(self)


class FixedChildren(Part):
    """Part that initializes a fixed dictionary as children

    The children are instantiated during __init__ and adopted by the
    class using this part. They cannot receive init argumentes, but
    could retrieve configuration from their parent.
    """
    fixed_children_factories = default(None)

    @plumb
    def __init__(_next, self, *args, **kw):
        _next(self, *args, **kw)
        self._children = odict()
        for key, factory in self.fixed_children_factories:
            child = factory()
            child.__name__ = key
            child.__parent__ = self
            self._children[key] = child

    @finalize
    def __delitem__(self, key):
        raise NotImplementedError("read-only")

    @finalize
    def __getitem__(self, key):
        return self._children[key]

    @finalize
    def __iter__(self):
        return iter(self._children)

    @finalize
    def __setitem__(self, key, val):
        raise NotImplementedError("read-only")


class GetattrChildren(Part):
    """Access children via getattr, given the attr name is unused
    """
    @finalize
    def __getattr__(self, name):
        """For new-style classes __getattr__ is called, if the
        attribute could not be found via MRO
        """
        return self.__getitem__(name)


class NodeChildValidate(Part):
    implements(INodeChildValidate)

    allow_non_node_childs = default(False)

    @plumb
    def __setitem__(_next, self, key, val):
        if not self.allow_non_node_childs and inspect.isclass(val):
            raise ValueError, u"It isn't allowed to use classes as values."
        if not self.allow_non_node_childs and not INode.providedBy(val):
            raise ValueError("Non-node childs are not allowed.")
        _next(self, key, val)


class Unicode(Part):
    """Plumbing element to ensure unicode for keys and string values.
    """
    # XXX: currently won't work, as the decode function is missing
    # check the one in bda.ldap.strcodec
    # XXX: It feels here it would be nice to be able to get an instance of a
    # plumbing to configure the codec.
    implements(IUnicode)

    @plumb
    def __delitem__(_next, self, key):
        if isinstance(key, str):
            key = decode(key)
        _next(key)

    @plumb
    def __getitem__(_next, self, key):
        if isinstance(key, str):
            key = decode(key)
        return _next(key)

    @plumb
    def __setitem__(_next, self, key, val):
        if isinstance(key, str):
            key = decode(key)
        if isinstance(val, str):
            val = decode(val)
        return _next(key, val)


class Wrap(Part):
    """Plumbing element that wraps nodes coming from deeper levels in a
    NodeNode.
    """
    implements(IWrap)

    @plumb
    def __getitem__(_next, self, key):
        val = _next(self, key)
        if INode.providedBy(val):
            val = NodeNode(val)
        return val

    @plumb
    def __setitem__(_next, self, key, val):
        if INode.providedBy(val):
            val = val.context
        _next(self, key, val)
