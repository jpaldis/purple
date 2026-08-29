'''
MIT Licence: Copyright (c) 2025 Baya Systems <https://bayasystems.com>

Purple implementation
======================

Purple state-update rules
'''

from . import common
import annotationlib


class Rule:
    def __init__(self, component, method, params):
        self.component = component
        self.method_name = method.__name__
        self.top_component = getattr(component, '_dp_top_component', None)
        self.method = method
        self.params = params

    def __str__(self):
        cmp_name = '.'.join(self.component.name)
        params = ', '.join(f'{n}={v}' for n,v in self.params.items())
        return f'{cmp_name}.{self.method_name}({params})'

    def invoke(self, check = True, print_headers = True, show_print = True):
        with Invocation(self) as invocation:
            self.method(**self.params)
        if check and invocation.exc_type is not None:
            raise invocation.exc_value
        if show_print and not invocation.guarded:
            invocation.produce_printout(headers = print_headers)
        return invocation


class LeafStateChange:
    def __init__(self, component, leaf_name, value_before, value_after):
        self.component = component
        self.top_component = component._dp_top_component
        self.leaf_name = leaf_name
        self.full_name_hash_a = hash((component.name, leaf_name))
        self.full_name_hash_b = hash((leaf_name, component.name))

        self.value_before = value_before
        self.value_after = value_after

    def hash_a_leaf(self, v):
        # leaf (or static-record in case of Union changing type) can define a
        # hash function separate from python's __hash__() so that it doesn't need
        # to follow the same rules
        hash_function = getattr(v, '_dp_hash_function', hash)
        try:
            hash_value = hash_function(v)
        except TypeError:
            print('Attempt to set leaf to unhashable type', type(v))
            print('    leaf name:', '.'.join(self.component.name) + '.' + self.leaf_name)
            print('    value:', v)
            raise

        # use two different name hashes; python's internal hash() isn't ideal
        return self.full_name_hash_a ^ self.full_name_hash_b * hash_value

    def update_model_state_hash(self, v_current, v_to):
        msh = self.top_component._dp_model_state_hash - self.hash_a_leaf(v_current) + self.hash_a_leaf(v_to)
        self.top_component._dp_raw_setattr('_dp_model_state_hash', msh)

    @staticmethod
    def require_equal(a, b):
        # some leaf state types have a custom __eq__ and don't allow equality testing for Undef
        try:
            assert a == b, f'{a} {b}'
        except common.ReadUnDefined:
            assert a._dp_eq__(b)

    def make_change(self, v_from, v_to, v_check):
        # leaf value changes from current_value to v_to
        v_current = self.component._dp_raw_getattr(self.leaf_name)
        if v_check is common.UniqueObject:
            v_check = v_from
        self.require_equal(v_check, v_current)
        self.update_model_state_hash(v_current, v_to)
        self.component._dp_raw_setattr(self.leaf_name, v_to)

    def apply(self, check_value = common.UniqueObject):
        self.make_change(self.value_before, self.value_after, check_value)

    def revert(self, check_value = common.UniqueObject):
        self.make_change(self.value_after, self.value_before, check_value)


class Invocation:
    '''Stores data about a Rule invocation: success/failure and the system state before and after
    '''
    def __init__(self, rule):
        self.rule = rule
        self.top_component = rule.top_component
        self.exc_type = None
        self.exc_value = None
        self.guarded = False
        self.state_changes = dict() # (component_name,leaf_name):LeafStateChange
        self.printout = []

    def __enter__(self):
        self.top_component._dp_raw_setattr('_dp_current_invocation', self)
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type:
            # FIXME
            # cannot revert state if the exception was caused by an unhashable leaf
            # so should detect such cases (they are fatal and make a mess for the user)
            self.revert_state()
            if exc_type is common.GuardFailed:
                self.guarded = True
            else:
                self.exc_type = exc_type
                self.exc_value = exc_value
        self.top_component._dp_raw_setattr('_dp_current_invocation', None)
        return True

    def leaf_state_change(self, component, leaf_attr_name, leaf_new_value):
        update_key = component.name, leaf_attr_name
        repeated_update = self.state_changes.get(update_key, None)
        if repeated_update is None:
            original_value = component._dp_raw_getattr(leaf_attr_name)
            check_value = original_value
        else:
            original_value = repeated_update.value_before
            check_value = repeated_update.value_after
        change = LeafStateChange(component, leaf_attr_name, original_value, leaf_new_value)
        self.state_changes[update_key] = change
        change.apply(check_value)

    def revert_state(self):
        for change in self.state_changes.values():
            change.revert()

    def apply_state(self):
        for change in self.state_changes.values():
            change.apply()

    def print(self, args, kwargs):
        self.printout.append((args, kwargs))

    def produce_printout(self, headers, file = None):
        for args, kwargs in self.printout:
            if file and 'file' not in kwargs:
                kwargs['file'] = file
            if headers:
                args = (self.rule, '::', *args)
            print(*args, **kwargs)


def construct_all(instance, method_name):
    ''' make a list of Rule objects from a method name, one per parameter set

    instance may be a class (for declaration-time testing) or an object being elaborated
    '''
    the_method = getattr(instance, method_name)
    annots = annotationlib.get_annotations(the_method)
    a_list = [a for a in annots.items() if a[0] != 'return']
    return [Rule(instance, the_method, pd) for pd in construct_all_recursive(a_list)]

def construct_all_recursive(param_items):
    if not param_items:
        yield dict()
    else:
        (first_pname, first_ptype),others = param_items[0], param_items[1:]
        for first_value in first_ptype._dp_all_possible_values():
            first_dict = {first_pname:first_value}
            for others_dict in construct_all_recursive(others):
                yield dict(**first_dict, **others_dict)
