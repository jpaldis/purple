'''
MIT Licence: Copyright (c) 2025 Baya Systems <https://bayasystems.com>

Purple implementation
======================

Purple hierarchical static state types

todo
    hierarchical override of initial-values
'''

import inspect
from . import common, rule, metaclass, clock


class Model(common.PurpleComponent, metaclass = metaclass.PurpleHierarchicalMetaClass):
    def __init__(self, name = 'top', is_top = True):
        if is_top:
            self._dp_raw_setattr('_dp_rules', [])
            self._dp_raw_setattr('_dp_current_invocation', None)
            leaf_state = self._dp_elaborate(name, self, None, tuple(), self._dp_initial_value)
            # leaf state is usually (component-object, leaf-name), but not for (static) union
            # initial value of state-hash is a functional don't-care
            self._dp_raw_setattr('_dp_model_state_hash', 0)

    def update(self, **values):
        '''in-place modification with values replacing named elements of self, hierarchically
        '''
        leaf_updates = self._dp_instance_update_leaf_changes(None, '', self, values)
        self._dp_announce_leaf_changes(leaf_updates)

    @classmethod
    def _dp_instance_setattr_leaf_changes(cls, owner, name, self, value):
        if value is common.UnDefined:
            value_list = [common.UnDefined for _ in cls._dp_state_types]
        elif value is common.UnSelected:
            value_list = [common.UnSelected for _ in cls._dp_state_types]
        else:
            value_list = [value._dp_raw_getattr(n) for n in cls._dp_state_types]
        leaf_updates = ()
        for (attr_name,attr_cls),value in zip(cls._dp_state_types.items(), value_list):
            current = self._dp_raw_getattr(attr_name)
            leaf_updates += attr_cls._dp_instance_setattr_leaf_changes(self, attr_name, current, value)
        return leaf_updates

    @classmethod
    def _dp_instance_update_leaf_changes(cls, owner, name, self, values):
        # may get a dict of changes, or a transient/static object reference to copy
        if isinstance(values, dict):
            leaf_updates = ()
            for attr_name,value in values.items():
                state_type = self._dp_state_types[attr_name]
                current = self._dp_raw_getattr(attr_name)
                leaf_updates += state_type._dp_instance_update_leaf_changes(self, attr_name, current, value)
        else:
            leaf_updates = cls._dp_instance_setattr_leaf_changes(owner, name, self, values)
        return leaf_updates

    @classmethod
    def _dp_elaborate(cls,
        name, top_component, instantiating_component, hierarchical_name, initial_value_dict
    ):
        ''' elaborate does 2 things
        creates a component
            except if called from __init__ in which case the component object already exists
                and a new system-top is being created
            hierarchically, so that component is elaborated
        returns the leaf state for system-top
        '''
        # add an object in the hierarchy, except for top
        if instantiating_component:
            self = cls(is_top = False)
            instantiating_component._dp_raw_setattr(name, self)
        else:
            self = top_component

        self._dp_raw_setattr('name', (*hierarchical_name, name))
        self._dp_raw_setattr('_dp_top_component', top_component)
        self._dp_raw_setattr('_dp_union_instances', dict())
        self._dp_top_component._dp_rules.extend(self._dp_construct_rules(self))
        leaf_state = self._dp_elaborate_substate(initial_value_dict)
        self._dp_elaborate_clocks()
        return leaf_state

    @classmethod
    def _dp_construct_rules(cls, self = None):
        rv = []
        instance = cls if self is None else self
        for rule_name in cls._dp_rule_names:
            rv.extend(rule.construct_all(instance, rule_name))
        return rv

    def _dp_elaborate_substate(self, initial_value_dict):
        leaf_state = ()
        for state_element_name,state_element_type in self._dp_state_types.items():
            initial_values = initial_value_dict[state_element_name]
            leaf_state += state_element_type._dp_elaborate(
                state_element_name, self._dp_top_component, self, self.name, initial_values)
        return leaf_state

    def __setattr__(self, attr_name, value):
        try:
            state_type = self._dp_state_types[attr_name]
        except KeyError:
            assert False, f'attempt to set a non-state attribute, {attr_name}'
        current = self._dp_raw_getattr(attr_name)
        leaf_updates = state_type._dp_instance_setattr_leaf_changes(self, attr_name, current, value)
        self._dp_announce_leaf_changes(leaf_updates)

    def _dp_announce_leaf_changes(self, leaf_updates):
        top = self._dp_top_component
        for o,n,v in leaf_updates:
            top._dp_current_invocation.leaf_state_change(o, n, v)

    @classmethod
    def _dp_add_rules_from_base(cls, base, typeproxy_class):
        ''' called on declaration of a Model subclass, once for every base

        base class has a set _dp_rule_names, which are copied to cls
        '''
        cls._dp_rule_names |= base._dp_rule_names

    @classmethod
    def _dp_add_rules_from_annotations(cls, typeproxy_class, raw_annotations):
        ''' called on declaration of a Model subclass

        cls annotations may have a list of rules, each being one of
            string name
            type-proxy (name)
            callable

        fills in cls._dp_rule_names
        constructs rule objects as a declaration-time test, on final call
        '''
        for state_element_name,state_element_type in raw_annotations.items():
            if state_element_name in ('rules', 'non_rules'):
                for rule_method in state_element_type:
                    if isinstance(rule_method, str):
                        rule_name = rule_method
                    elif isinstance(rule_method, typeproxy_class):
                        assert len(rule_method.name) == 1
                        rule_name = rule_method.name[0]
                    elif inspect.isfunction(rule_method):
                        rule_name = rule_method.__name__

                    if state_element_name == 'non_rules':
                        cls._dp_rule_names.remove(rule_name)
                    else:
                        cls._dp_rule_names.add(rule_name)

        if cls._dp_rule_names:
            # make rules and discard (test on declaration)
            cls._dp_construct_rules()

    @classmethod
    def _dp_add_bindings_from_base(cls, base):
        ''' called on declaration of a Model subclass, once for every base

        FIXME this does not allow for array size changes from base to subclass
            does it matter - what is the use case?
        '''
        cls._dp_bindings.extend(base._dp_bindings)

    @classmethod
    def _dp_add_bindings_from_annotations(cls, raw_cls_bindings):
        ''' called on declaration of a Model subclass

        FIXME:
            unclear how to deal with collisions/fan-in/fan-out/bases: ordered list and take last one?
            replace LHS?
            use +>> and +<< operators for fans?
        '''
        def get_array_length(purple_cls, allow_unknown, unknown_length):
            array_length = getattr(purple_cls, '_dp_array_length', -1)
            if array_length > 0:
                return array_length
            elif allow_unknown:
                return unknown_length
            else:
                assert False, 'trying to array-bind a non-array or handler-array on right-hand-side'

        def make_subnames(purple_cls, name, allow_unknown, unknown_length = 1):
            # recursive expansion of slices, and conversion of int to string names
            car = name[0]
            cdr = name[1:]

            if isinstance(car, int):
                assert 0 <= car < get_array_length(purple_cls, allow_unknown, car + 1)
                new_cars = [purple_cls._dp_array_2attrname(car)]
            elif isinstance(car, slice):
                indices = range(get_array_length(purple_cls, allow_unknown, unknown_length))[car]
                new_cars = [purple_cls._dp_array_2attrname(c) for c in indices]
            else:
                new_cars = [car]

            if cdr:
                # all elements of an array have the same type so take the first one
                next_purple_cls = purple_cls._dp_state_types.get(new_cars[0], None)
                if next_purple_cls is None:
                    # binding must be referring to a HandlerArray, which can have an index or a slice
                    ha = vars(purple_cls)[new_cars[0]]
                    assert isinstance(ha, metaclass.HandlerArray)
                    assert len(cdr) == 1, 'cannot have hierarchy below a handler-arrray'
                    array_length = get_array_length(type(ha), allow_unknown, unknown_length)
                    # force handler methods to exist
                    return [(ha.ensure_indexed_method(i, purple_cls),) for i in range(array_length)[cdr[0]]]
                else:
                    lower_names = make_subnames(next_purple_cls, cdr, allow_unknown, unknown_length)
                    return [(c, *n) for c in new_cars for n in lower_names]
            else:
                return [(c,) for c in new_cars]

        # search for array indices and convert to strings according to the class definition
        # and blow up slices to separate single-bindings
        for b in raw_cls_bindings:
            # shortcut for non-array cases
            if not any(isinstance(n, (int, slice)) for n in (b.lhs.name + b.rhs.name)):
                cls._dp_bindings.append(b)
                continue

            # replace array indices with strings and expand array slices to individual bindings
            # LHS is always known-length
            # final slice on RHS might be a handler-array so work out the length it needs to match LHS
            lhs_names = make_subnames(cls, b.lhs.name, False)
            rhs_names = make_subnames(cls, b.rhs.name, True)
            len_lhs_names = len(lhs_names)
            len_rhs_names = len(rhs_names)
            if len_lhs_names != len_rhs_names:
                unknown_len = len_lhs_names // len_rhs_names
                assert unknown_len * len_rhs_names == len_lhs_names, 'bind to handler-array has bad length'
                rhs_names = make_subnames(cls, b.rhs.name, True, unknown_len)
            assert len(rhs_names) == len_lhs_names

            for lhs,rhs in zip(lhs_names, rhs_names):
                lhs_proxy = metaclass.PurpleTypeProxy('', lhs)
                rhs_proxy = metaclass.PurpleTypeProxy('', rhs)
                b = metaclass.Binding(lhs_proxy, rhs_proxy, b.left2right, add_to_mcs = False)
                cls._dp_bindings.append(b)

    @classmethod
    def _dp_add_clocks_from_base(cls, base):
        ''' called on declaration of a Model subclass, once for every base
        '''
        cls._dp_clock_declarations.update(base._dp_clock_declarations)

    @classmethod
    def _dp_add_clocks_from_annotations(cls, raw_annotations):
        ''' called on declaration of a Model subclass
        '''
        for k,v in raw_annotations.items():
            if isinstance(v, clock.Clock):
                cls._dp_clock_declarations[k] = v

    def _dp_elaborate_clocks(self):
        '''convert clock references into actual clock objects with associated rules
        '''
        clocks = {k:v.elaborate(self) for k,v in self._dp_clock_declarations.items()}
        self._dp_raw_setattr('_dp_clocks', clocks)

    def find_rule(self, component = None, method_name = '', params = dict()):
        'generator which filters all rules in the system'
        for the_rule in self._dp_rules:
            if not (component is None or component is the_rule.component):
                continue
            if method_name not in ('', the_rule.method_name):
                continue
            if any(n not in the_rule.params or the_rule.params[n] != v for n,v in params.items()):
                continue
            yield the_rule

    def find_clock(self, component = None, name = ''):
        'generator which filters all clocks in the system'
        if component in (None, self):
            for clock_name,clock in self._dp_clocks.items():
                if name in ('', clock_name) and not clock.driven_by_another_clock:
                    yield clock

        for state_element_name in self._dp_state_types:
            subcomponent = self._dp_raw_getattr(state_element_name)
            if isinstance(subcomponent, Model):
                yield from subcomponent.find_clock(component, name)
