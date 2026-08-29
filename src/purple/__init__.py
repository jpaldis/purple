'''
MIT Licence: Copyright (c) 2025 Baya Systems <https://bayasystems.com>

Purple implementation
======================

lint is not fully clean and probably cannot be, but valuable
    ruff check src --exclude __init__.py
    ruff check tst --ignore F821 --ignore F811 --ignore E722

FIXME
    still have an occasional bug in rob_implementation test
        list index out of range
        File "/home/purple/tst_verif/rob_implementation_test.py", line 399, in requester_clk
        txn_at_completer = txns_at_completer[0][1]
    with 3.13 elaboration is not deterministic; fix this in 3.14
        problem seems to be the order of rules, which can affect randomised simulators
    state variable type for clocked sim integer where two processes change the value
        eg num_outstanding: DualProcessCounter[limit]
        def clocked(self):
            num_outstanding += 1
            if num_outstanding == 57: do_stuff()
        def handled(self):
            if num_outstanding == 57: do_stuff()
            num_outstanding -= 1
        only possible for commutative operations eg not for (+1) and (*2)
        Tuple[] also has compatible operations eg append an item and modify another item
        only needed for clocked-simulator (but should work for atomic-rule)

        Model.__setattr__ calls Leaf.instance-setattr then Model.announce-leaf-changes
        leaf instance-setattr returns tuple(owner, name, cast_value)
        announce-leaf-changes calls current-invocation.leaf-state-change
        this stores a dict of leaf-updates and applies the change to the Model
        each leaf only has one entry, it gets merged if changed again
        each leaf-state-change has a value-before and a value-after and tests that when
        being applied or reverted, the current state is what it should be

        AtomicRuleSimulator invokes rules in sequence and may revert/apply as part
        of testing rules but doesn't need to combine invocations

        Clock.event invokes all the selected rules, reverting between each
        then it re-applies all successful rules
        so
            leaf instance-setattr could return an additional thing to indicate a mergeable operation
            Clock.event could flatten all the leaf changes from all concurrent rules
            then merge those that are to the same leaf - to a single normal LeafStateChange
            so the MergeableOperation would just be an operation-type (values are there anyway)
            and the LeafStateChange.merge(other) would just execute them in some order
                eg tuple.delete would need to go in index order

            a mergeable operation may be already merged, which would have to happen
            even for single-rule.  eg if you delete twice from a tuple at index 4 and 10
            so that the replace at index 6 can be put between them.
            looks like for Tuple, MergeableOperation would need to contain a list of ops
            but for UpDownCounter it would only need a single op combined on the fly

            incompatible ops: set-tuple-to-x is not compatible with append-to-tuple
            and set-counter is not compatible with add-to-counter
            so you may have to check that everything is an op
            don't yet see a leaf with 2 or more disjoint sets of compatible ops,
            or that this could be useful

            don't try to support for Leaf-in-Union

        at the moment we don't have a "revert clock event" capability
        a merged list of leaf updates might be a way to do that

    add a frozen-Dictionary leaf type basically the same as Tuple
    add a GuardedInteger[] which guards instead of errors if outside range
    declaring a state type as Tuple not Tuple[XYZ] fails silently
    start rules
        can there be more than one?  can they have parameters?
        class X(Model):
            b: SomeType
            end_of_elaboration: make_b
            def make_b(self): self.b = blah
        can we have a factory option for initial values?  see below array-index-initialiser
        class X(Model):
            b: SomeType = Initialiser[make_b]
            def make_b(self): return blah
    clocked simulator should include time in rule printout headers
    invariants
    rules with parameters get very slow
        rather than generating a separate rule for each parameter set during elaboration
        choose a parameter set after rule selection, by randomisation of record/leaf
        saves memory, saves startup time, might increase simulation time
    coverage definition methods
    array with enum keys
        myarray: Array[enum_class, element_class] = {dict_of_initial_values}
    save/restore
    test ability to suppress a rule in subclass
    cosimulation with Verilog-DPI
    does Interface generalise to using registered-output port and initial values?
    add randomisation capability to records and leaves
        select among all-possible-values, or create on-the-fly?
        don't create all values till first call, or require a randomiser object to be created
        allow invariants in Record to reduce number of options?
    when you get a clocked-rule name wrong in Clock[rule_name] you get a very confusing error
    bug: can't have Tuple of Leaf
        this is temporarily hacked to work, but
        coding style is bad - test for leaf in Tuple - use LeafMetaClass?
        no protection against transient BitVector being in-place modifiable (so non-undoable state change)
        so need frozen bitvectors (Leaf already plans for this)?
    where a leaf has an object type (like Tuple or BitVector or Modulo) it would be nice to be able
        to derive new object types in a relatively easy way
        currently needs re-write of the Generic to use the derived class
        use case: I tried to add a method to Tuple
    configurable models
        how to have an array of non-identical things (eg buffers of different message types or different lengths)
            myarray: Array[list_of_types] = [list_of_initial_values]
            mycomponents: Subcomponents[dict_of_types] = {dict_of_initial_values}
                # this gives you whatever names you want matched to whatever types
                # dict should support any of integer/enum/string keys, same keys for types and initial-values
    can I have a Tuple of Union?  test it
    change Generic so that it sets the class name to something useful unless it has been overridden
    change Generic so that if the function does not return a class, return the most recently created purple subclass
        and do this in all the src uses of Generic
    array-index variant allowing modification after elab
        only sets initial value
        question is: what are the limits on modifications?
        class X(Record):
            a: Integer[0,100] = ArrayIndexInitialiser
            b: ArrayIndex
            c: MutableArrayIndex[Integer[0,100]]
            d0: Integer[0, 100] = ArrayIndex
            d1: Const[ArrayIndex]
    for Python without GIL, simulators should be able to explore rules in parallel from the same system state
        this implies having multiple testbenches within a simulator, with synchronised state
        allocate a decent number of rules to each testbench, because we will synchronise after one step
        are state hashes protable across testbenches?
        1. atomic rule simulation
            1.1 searching for a rule at random
                run all rules; synchronise; select a rule to commit; apply its state to all testbenches; repeat
                this can reduce the number of random single trials before giving up and going systematic
                speeds you up if a high proportion of rules are guarded
                slows you down a bit when most rules are runnable
            1.2 verification search for any rule that works
                main value (what is slowest now) is proving there's no possible rule sequence that matches stimulus
                so is it as simple as running a load of check-search in parallel, only starting with a subset of rules?
                do that and some threads will rapidly fail and then need to be re-deployed
                need a new algorithm
                when it is failing, will eventually run all rules so can do that in parallel
                but when not failing this may be wasteful
        2. clocked simulation
            if there are many rules, just divide them among simulators/threads
            at end of clock cycle apply all state updates to all simulators


cleanup
    documentation
    move or copy all open issues/fixmes to documentation or GH issues
    some fixmes are out of date and have been fixed
    am I allowing partially-undef records to be compared for equality?  is it OK?
    search for all " if _dp_class_is_something " and try to replace with classmethods
        then define clearly what the expected classmethod behaviour is
    improve all Exceptions to trap specific things eg CastToLeafFailure
    can raise exceptions higher up in the stack, to hide your internals...
        eg in rule.invoke or invocation.__exit__, do something like the following
        to hide PurpleException.assert and other layers of purple mess
        "raise Exception("foo occurred").with_traceback(tracebackobj)"
        If the traceback of the active exception is modified in an except clause, a subsequent raise statement re-raises the exception with the modified traceback.  also true for __exit__? do we even re-raise or just print
        and offer to post-mortem or re-run?
    names of generated classes
    good error messages, eg if combined initial values don't match any union option
    type checking on class declaration
        rules are type-annotated with (finite?) Record and Leaf types
        ports bind to handlers with the right Record/Leaf type
        ports bind to ports with the right Record/Leaf type
        port payload type is a record or a leaf
        ports bind in the right direction and fan in/out is controlled
        state elements have Purple class types
        suppress checking option for abstract base classes (may need to re-run annotation evaluation?)
    replace star-import with named set of things in this file __init__.py
    support copying records from superclasses and subclasses?
    bad error message when clocked-process name is misspelt

tests todo
    model (more tests)
    inheritance (record or model) including multi-inheritance and multi-level and overrides
    enum, boolean, constant
    parameterised model and record including partial-specialisation
    shallow and deep copy of static-records to/from transient-records

could this go full-bs?
    that is run a clocked simulation from a set of atomic rules
    attempt to invoke all rules in every clock cycle, from same start state
        assume any pair of rules that overlap cannot be run in the same clock cycle
        needs some arbitration to select between collisions
        does this require knowledge of which rules are reading which parts of system state?
        is it limited to rules without parameters, if parameters represent external stimulus?
    even further
        allow one rule to forward state to another, so the 2 can run sequentially
            in the same cycle
        allow a rule to need multiple clock cycles to complete
            does it read per cycle but hold all writes till the end?
            so that it can be abandoned if atomicity was violated during run
            can you pipeline, so multiple instances of the same rule
                read all at the start?

could add a VCD generation, but possibly only useful for clocked and only for state elements
        that are some kind of finite-integer or boolean (or constructed from them).
    could add an optional VCD method to leaf classes that by default raises an error
    would also need to support functions that get the current value of something, in case
        VCD needs to include the output of combinatorial logic.  these will return Record or
        int or bool and will not always have a known Purple type
'''

from .__about__ import __version__

from .common import *
from .record import *
from .model import *
from .static_record import *
from .leaf import *
from .port import *
from .union import *
from .array import *
from .state import *
from .tuple import *
from .bitvector import *
from .clock import *
from .parameterise import *
from .interface import *
from .simulator import *
from .verif import *
from .metaclass import AddToState, HandlerArray
