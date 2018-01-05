"""
Other functions
"""
from __future__ import print_function
from six.moves import range
from six import integer_types

from sage.symbolic.function import GinacFunction, BuiltinFunction
from sage.symbolic.expression import Expression
from sage.libs.pynac.pynac import (register_symbol, symbol_table,
        py_factorial_py, I)
from sage.symbolic.all import SR
from sage.rings.all import Integer, Rational, RealField, ZZ, ComplexField
from sage.rings.complex_number import is_ComplexNumber
from sage.misc.latex import latex
from sage.misc.decorators import rename_keyword
import math

from sage.structure.element import coercion_model

# avoid name conflicts with `parent` as a function parameter
from sage.structure.all import parent as s_parent

from sage.symbolic.constants import pi
from sage.functions.log import exp
from sage.functions.trig import arctan2
from sage.functions.exp_integral import Ei
from sage.libs.mpmath import utils as mpmath_utils
from sage.arith.all import binomial as arith_binomial

one_half = SR.one() / SR(2)


class Function_abs(GinacFunction):
    def __init__(self):
        r"""
        The absolute value function.

        EXAMPLES::

            sage: var('x y')
            (x, y)
            sage: abs(x)
            abs(x)
            sage: abs(x^2 + y^2)
            abs(x^2 + y^2)
            sage: abs(-2)
            2
            sage: sqrt(x^2)
            sqrt(x^2)
            sage: abs(sqrt(x))
            sqrt(abs(x))
            sage: complex(abs(3*I))
            (3+0j)

            sage: f = sage.functions.other.Function_abs()
            sage: latex(f)
            \mathrm{abs}
            sage: latex(abs(x))
            {\left| x \right|}
            sage: abs(x)._sympy_()
            Abs(x)

        Test pickling::

            sage: loads(dumps(abs(x)))
            abs(x)

        TESTS:

        Check that :trac:`12588` is fixed::

            sage: abs(pi*I)
            pi
            sage: abs(pi*I*catalan)
            catalan*pi
            sage: abs(pi*catalan*x)
            catalan*pi*abs(x)
            sage: abs(pi*I*catalan*x)
            catalan*pi*abs(x)
            sage: abs(1.0j*pi)
            1.00000000000000*pi
            sage: abs(I*x)
            abs(x)
            sage: abs(I*pi)
            pi
            sage: abs(I*log(2))
            log(2)
            sage: abs(I*e^5)
            e^5
            sage: abs(log(1/2))
            -log(1/2)
            sage: abs(log(3/2))
            log(3/2)
            sage: abs(log(1/2)*log(1/3))
            log(1/2)*log(1/3)
            sage: abs(log(1/2)*log(1/3)*log(1/4))
            -log(1/2)*log(1/3)*log(1/4)
            sage: abs(log(1/2)*log(1/3)*log(1/4)*i)
            -log(1/2)*log(1/3)*log(1/4)
            sage: abs(log(x))
            abs(log(x))
            sage: abs(zeta(I))
            abs(zeta(I))
            sage: abs(e^2*x)
            abs(x)*e^2
            sage: abs((pi+e)*x)
            (pi + e)*abs(x)
        """
        GinacFunction.__init__(self, "abs", latex_name=r"\mathrm{abs}",
                               conversions=dict(sympy='Abs',
                                                mathematica='Abs',
                                                giac='abs'))

abs = abs_symbolic = Function_abs()


@rename_keyword(deprecation=22079, maximum_bits="bits")
def _eval_floor_ceil(self, x, method, bits=0, **kwds):
    """
    Helper function to compute ``floor(x)`` or ``ceil(x)``.

    INPUT:

    - ``x`` -- a number

    - ``method`` -- should be either ``"floor"`` or ``"ceil"``

    - ``bits`` -- how many bits to use before giving up

    See :class:`Function_floor` and :class:`Function_ceil` for examples
    and tests.

    TESTS::

        sage: numbers = [SR(10^100 + exp(-100)), SR(10^100 - exp(-100)), SR(10^100)]
        sage: numbers += [-n for n in numbers]
        sage: for n in numbers:
        ....:     f = floor(n)
        ....:     c = ceil(n)
        ....:     if f == c:
        ....:         assert n in ZZ
        ....:     else:
        ....:         assert f + 1 == c

    A test from :trac:`12121`::

        sage: e1 = pi - continued_fraction(pi).convergent(2785)
        sage: e2 = e - continued_fraction(e).convergent(1500)
        sage: f = e1/e2
        sage: f = 1 / (f - continued_fraction(f).convergent(1000))
        sage: f = f - continued_fraction(f).convergent(1)
        sage: floor(f, bits=10000)
        -1
        sage: ceil(f, bits=10000)
        0

    These don't work but fail gracefully::

        sage: ceil(Infinity)
        Traceback (most recent call last):
        ...
        ValueError: Calling ceil() on infinity or NaN
        sage: ceil(NaN)
        Traceback (most recent call last):
        ...
        ValueError: Calling ceil() on infinity or NaN

    TESTS::

        sage: floor(pi, maximum_bits=0)
        doctest:...: DeprecationWarning: use the option 'bits' instead of 'maximum_bits'
        See http://trac.sagemath.org/22079 for details.
        3
    """
    # First, some obvious things...
    try:
        m = getattr(x, method)
    except AttributeError:
        pass
    else:
        return m()

    if isinstance(x, integer_types):
        return Integer(x)
    if isinstance(x, (float, complex)):
        m = getattr(math, method)
        return Integer(m(x))
    if type(x).__module__ == 'numpy':
        import numpy
        m = getattr(numpy, method)
        return m(x)

    # The strategy is to convert the number to an interval field and
    # hope that this interval will have a unique floor/ceiling.
    #
    # There are 2 reasons why this could fail:
    # (A) The expression is very complicated and we simply require
    #     more bits.
    # (B) The expression is a non-obvious exact integer. In this
    #     case, adding bits will not help since an interval around
    #     an integer will not have a unique floor/ceiling, no matter
    #     how many bits are used.
    #
    # The strategy is to first reduce the absolute diameter of the
    # interval until its size is at most 10^(-6). Then we check for
    # (B) by simplifying the expression.
    from sage.rings.all import RealIntervalField

    # Might it be needed to simplify x? This only applies for
    # elements of SR.
    need_to_simplify = (s_parent(x) is SR)

    # An integer which is close to x. We use this to increase precision
    # by subtracting this guess before converting to an interval field.
    # This mostly helps with the case that x is close to, but not equal
    # to, an exact integer.
    guess = Integer(0)

    # We do not use the target number of bits immediately, we just use
    # it as indication of when to stop.
    target_bits = bits
    bits = 32
    attempts = 5
    while attempts:
        attempts -= 1
        if not attempts and bits < target_bits:
            # Add one more attempt as long as the precision is less
            # than requested
            attempts = 1

        RIF = RealIntervalField(bits)
        if guess:
            y = x - guess
        else:
            y = x
        try:
            y_interval = RIF(y)
        except TypeError:
            # If we cannot compute a numerical enclosure, leave the
            # expression unevaluated.
            return BuiltinFunction.__call__(self, SR(x))
        diam = y_interval.absolute_diameter()
        if diam.is_infinity():
            # We have a very bad approximation => increase the number
            # of bits a lot
            bits *= 4
            continue
        fdiam = float(diam)
        if fdiam >= 1.0:
            # Increase number of bits to get to a diameter less than
            # 2^(-32), assuming that the diameter scales as 2^(-bits)
            bits += 32 + int(diam.log2())
            continue

        # Compute ceil/floor of both ends of the interval:
        # if these match, we are done!
        a = getattr(y_interval.lower(), method)()
        b = getattr(y_interval.upper(), method)()
        if a == b:
            return a + guess

        # Compute a better guess for the next attempt. Since diam < 1,
        # there is a unique integer in our interval. This integer equals
        # the ceil of the lower bound and the floor of the upper bound.
        if self is floor:
            guess += b
        else:
            assert self is ceil
            guess += a

        if need_to_simplify and fdiam <= 1e-6:
            x = x.full_simplify().canonicalize_radical()
            need_to_simplify = False
            continue

        bits *= 2

    raise ValueError("cannot compute {}({!r}) using {} bits of precision".format(method, x, RIF.precision()))


class Function_ceil(BuiltinFunction):
    def __init__(self):
        r"""
        The ceiling function.

        The ceiling of `x` is computed in the following manner.


        #. The ``x.ceil()`` method is called and returned if it
           is there. If it is not, then Sage checks if `x` is one of
           Python's native numeric data types. If so, then it calls and
           returns ``Integer(math.ceil(x))``.

        #. Sage tries to convert `x` into a
           ``RealIntervalField`` with 53 bits of precision. Next,
           the ceilings of the endpoints are computed. If they are the same,
           then that value is returned. Otherwise, the precision of the
           ``RealIntervalField`` is increased until they do match
           up or it reaches ``bits`` of precision.

        #. If none of the above work, Sage returns a
           ``Expression`` object.


        EXAMPLES::

            sage: a = ceil(2/5 + x)
            sage: a
            ceil(x + 2/5)
            sage: a(x=4)
            5
            sage: a(x=4.0)
            5
            sage: ZZ(a(x=3))
            4
            sage: a = ceil(x^3 + x + 5/2); a
            ceil(x^3 + x + 5/2)
            sage: a.simplify()
            ceil(x^3 + x + 1/2) + 2
            sage: a(x=2)
            13

        ::

            sage: ceil(sin(8)/sin(2))
            2

        ::

            sage: ceil(5.4)
            6
            sage: type(ceil(5.4))
            <type 'sage.rings.integer.Integer'>

        ::

            sage: ceil(factorial(50)/exp(1))
            11188719610782480504630258070757734324011354208865721592720336801
            sage: ceil(SR(10^50 + 10^(-50)))
            100000000000000000000000000000000000000000000000001
            sage: ceil(SR(10^50 - 10^(-50)))
            100000000000000000000000000000000000000000000000000

        Small numbers which are extremely close to an integer are hard to
        deal with::

            sage: ceil((33^100 + 1)^(1/100))
            Traceback (most recent call last):
            ...
            ValueError: cannot compute ceil(...) using 256 bits of precision

        This can be fixed by giving a sufficiently large ``bits`` argument::

            sage: ceil((33^100 + 1)^(1/100), bits=500)
            Traceback (most recent call last):
            ...
            ValueError: cannot compute ceil(...) using 512 bits of precision
            sage: ceil((33^100 + 1)^(1/100), bits=1000)
            34

        ::

            sage: ceil(sec(e))
            -1

            sage: latex(ceil(x))
            \left \lceil x \right \rceil
            sage: ceil(x)._sympy_()
            ceiling(x)

        ::

            sage: import numpy
            sage: a = numpy.linspace(0,2,6)
            sage: ceil(a)
            array([ 0.,  1.,  1.,  2.,  2.,  2.])

        Test pickling::

            sage: loads(dumps(ceil))
            ceil
        """
        BuiltinFunction.__init__(self, "ceil",
                                   conversions=dict(maxima='ceiling',
                                                    sympy='ceiling',
                                                    giac='ceil'))

    def _print_latex_(self, x):
        r"""
        EXAMPLES::

            sage: latex(ceil(x)) # indirect doctest
            \left \lceil x \right \rceil
        """
        return r"\left \lceil %s \right \rceil"%latex(x)

    #FIXME: this should be moved to _eval_
    def __call__(self, x, **kwds):
        """
        Allows an object of this class to behave like a function. If
        ``ceil`` is an instance of this class, we can do ``ceil(n)`` to get
        the ceiling of ``n``.

        TESTS::

            sage: ceil(SR(10^50 + 10^(-50)))
            100000000000000000000000000000000000000000000000001
            sage: ceil(SR(10^50 - 10^(-50)))
            100000000000000000000000000000000000000000000000000
            sage: ceil(int(10^50))
            100000000000000000000000000000000000000000000000000
            sage: ceil((1725033*pi - 5419351)/(25510582*pi - 80143857))
            -2
        """
        return _eval_floor_ceil(self, x, "ceil", **kwds)

    def _eval_(self, x):
        """
        EXAMPLES::

            sage: ceil(x).subs(x==7.5)
            8
            sage: ceil(x)
            ceil(x)
        """
        try:
            return x.ceil()
        except AttributeError:
            if isinstance(x, integer_types):
                return Integer(x)
            elif isinstance(x, (float, complex)):
                return Integer(math.ceil(x))
        return None

ceil = Function_ceil()


class Function_floor(BuiltinFunction):
    def __init__(self):
        r"""
        The floor function.

        The floor of `x` is computed in the following manner.


        #. The ``x.floor()`` method is called and returned if
           it is there. If it is not, then Sage checks if `x` is one
           of Python's native numeric data types. If so, then it calls and
           returns ``Integer(math.floor(x))``.

        #. Sage tries to convert `x` into a
           ``RealIntervalField`` with 53 bits of precision. Next,
           the floors of the endpoints are computed. If they are the same,
           then that value is returned. Otherwise, the precision of the
           ``RealIntervalField`` is increased until they do match
           up or it reaches ``bits`` of precision.

        #. If none of the above work, Sage returns a
           symbolic ``Expression`` object.


        EXAMPLES::

            sage: floor(5.4)
            5
            sage: type(floor(5.4))
            <type 'sage.rings.integer.Integer'>
            sage: var('x')
            x
            sage: a = floor(5.4 + x); a
            floor(x + 5.40000000000000)
            sage: a.simplify()
            floor(x + 0.4000000000000004) + 5
            sage: a(x=2)
            7

        ::

            sage: floor(cos(8) / cos(2))
            0
            sage: floor(log(4) / log(2))
            2
            sage: a = floor(5.4 + x); a
            floor(x + 5.40000000000000)
            sage: a.subs(x==2)
            7
            sage: floor(log(2^(3/2)) / log(2) + 1/2)
            2
            sage: floor(log(2^(-3/2)) / log(2) + 1/2)
            -1

        ::

            sage: floor(factorial(50)/exp(1))
            11188719610782480504630258070757734324011354208865721592720336800
            sage: floor(SR(10^50 + 10^(-50)))
            100000000000000000000000000000000000000000000000000
            sage: floor(SR(10^50 - 10^(-50)))
            99999999999999999999999999999999999999999999999999
            sage: floor(int(10^50))
            100000000000000000000000000000000000000000000000000

        Small numbers which are extremely close to an integer are hard to
        deal with::

            sage: floor((33^100 + 1)^(1/100))
            Traceback (most recent call last):
            ...
            ValueError: cannot compute floor(...) using 256 bits of precision

        This can be fixed by giving a sufficiently large ``bits`` argument::

            sage: floor((33^100 + 1)^(1/100), bits=500)
            Traceback (most recent call last):
            ...
            ValueError: cannot compute floor(...) using 512 bits of precision
            sage: floor((33^100 + 1)^(1/100), bits=1000)
            33

        ::

            sage: import numpy
            sage: a = numpy.linspace(0,2,6)
            sage: floor(a)
            array([ 0.,  0.,  0.,  1.,  1.,  2.])
            sage: floor(x)._sympy_()
            floor(x)

        Test pickling::

            sage: loads(dumps(floor))
            floor
        """
        BuiltinFunction.__init__(self, "floor",
                                 conversions=dict(sympy='floor', giac='floor'))

    def _print_latex_(self, x):
        r"""
        EXAMPLES::

            sage: latex(floor(x))
            \left \lfloor x \right \rfloor
        """
        return r"\left \lfloor %s \right \rfloor"%latex(x)

    #FIXME: this should be moved to _eval_
    def __call__(self, x, **kwds):
        """
        Allows an object of this class to behave like a function. If
        ``floor`` is an instance of this class, we can do ``floor(n)`` to
        obtain the floor of ``n``.

        TESTS::

            sage: floor(SR(10^50 + 10^(-50)))
            100000000000000000000000000000000000000000000000000
            sage: floor(SR(10^50 - 10^(-50)))
            99999999999999999999999999999999999999999999999999
            sage: floor(int(10^50))
            100000000000000000000000000000000000000000000000000
            sage: floor((1725033*pi - 5419351)/(25510582*pi - 80143857))
            -3
        """
        return _eval_floor_ceil(self, x, "floor", **kwds)

    def _eval_(self, x):
        """
        EXAMPLES::

            sage: floor(x).subs(x==7.5)
            7
            sage: floor(x)
            floor(x)
        """
        try:
            return x.floor()
        except AttributeError:
            if isinstance(x, integer_types):
                return Integer(x)
            elif isinstance(x, (float, complex)):
                return Integer(math.floor(x))
        return None

floor = Function_floor()

class Function_Order(GinacFunction):
    def __init__(self):
        r"""
        The order function.

        This function gives the order of magnitude of some expression,
        similar to `O`-terms.

        .. SEEALSO::

            :meth:`~sage.symbolic.expression.Expression.Order`,
            :mod:`~sage.rings.big_oh`

        EXAMPLES::

            sage: x = SR('x')
            sage: x.Order()
            Order(x)
            sage: (x^2 + x).Order()
            Order(x^2 + x)
            sage: x.Order()._sympy_()
            O(x)

        TESTS:

        Check that :trac:`19425` is resolved::

            sage: x.Order().operator()
            Order
        """
        GinacFunction.__init__(self, "Order",
                conversions=dict(sympy='O'),
                latex_name=r"\mathcal{O}")

Order = Function_Order()

class Function_frac(BuiltinFunction):
    def __init__(self):
        r"""
        The fractional part function `\{x\}`.

        ``frac(x)`` is defined as `\{x\} = x - \lfloor x\rfloor`.

        EXAMPLES::

            sage: frac(5.4)
            0.400000000000000
            sage: type(frac(5.4))
            <type 'sage.rings.real_mpfr.RealNumber'>
            sage: frac(456/123)
            29/41
            sage: var('x')
            x
            sage: a = frac(5.4 + x); a
            frac(x + 5.40000000000000)
            sage: frac(cos(8)/cos(2))
            cos(8)/cos(2)
            sage: latex(frac(x))
            \operatorname{frac}\left(x\right)
            sage: frac(x)._sympy_()
            frac(x)

        Test pickling::

            sage: loads(dumps(floor))
            floor
        """
        BuiltinFunction.__init__(self, "frac",
                                 conversions=dict(sympy='frac'),
                                 latex_name=r"\operatorname{frac}")

    def _evalf_(self, x, **kwds):
        """
        EXAMPLES::

            sage: frac(pi).n()
            0.141592653589793
            sage: frac(pi).n(200)
            0.14159265358979323846264338327950288419716939937510582097494
        """
        return x - floor(x)

    def _eval_(self, x):
        """
        EXAMPLES::

            sage: frac(x).subs(x==7.5)
            0.500000000000000
            sage: frac(x)
            frac(x)
        """
        try:
            return x - x.floor()
        except AttributeError:
            if isinstance(x, integer_types):
                return Integer(0)
            elif isinstance(x, (float, complex)):
                return x - Integer(math.floor(x))
            elif isinstance(x, Expression):
                ret = floor(x)
                if not hasattr(ret, "operator") or not ret.operator() == floor:
                    return x - ret
        return None

frac = Function_frac()


class Function_gamma(GinacFunction):
    def __init__(self):
        r"""
        The Gamma function.  This is defined by

        .. MATH::

            \Gamma(z) = \int_0^\infty t^{z-1}e^{-t} dt

        for complex input `z` with real part greater than zero, and by
        analytic continuation on the rest of the complex plane (except
        for negative integers, which are poles).

        It is computed by various libraries within Sage, depending on
        the input type.

        EXAMPLES::

            sage: from sage.functions.other import gamma1
            sage: gamma1(CDF(0.5,14))
            -4.0537030780372815e-10 - 5.773299834553605e-10*I
            sage: gamma1(CDF(I))
            -0.15494982830181067 - 0.49801566811835607*I

        Recall that `\Gamma(n)` is `n-1` factorial::

            sage: gamma1(11) == factorial(10)
            True
            sage: gamma1(6)
            120
            sage: gamma1(1/2)
            sqrt(pi)
            sage: gamma1(-1)
            Infinity
            sage: gamma1(I)
            gamma(I)
            sage: gamma1(x/2)(x=5)
            3/4*sqrt(pi)

            sage: gamma1(float(6))  # For ARM: rel tol 3e-16
            120.0
            sage: gamma(6.)
            120.000000000000
            sage: gamma1(x)
            gamma(x)

        ::

            sage: gamma1(pi)
            gamma(pi)
            sage: gamma1(i)
            gamma(I)
            sage: gamma1(i).n()
            -0.154949828301811 - 0.498015668118356*I
            sage: gamma1(int(5))
            24

        ::

            sage: conjugate(gamma(x))
            gamma(conjugate(x))

        ::

            sage: plot(gamma1(x),(x,1,5))
            Graphics object consisting of 1 graphics primitive

        To prevent automatic evaluation use the ``hold`` argument::

            sage: gamma1(1/2,hold=True)
            gamma(1/2)

        To then evaluate again, we currently must use Maxima via
        :meth:`sage.symbolic.expression.Expression.simplify`::

            sage: gamma1(1/2,hold=True).simplify()
            sqrt(pi)

        TESTS:

            sage: gamma(x)._sympy_()
            gamma(x)

        We verify that we can convert this function to Maxima and
        convert back to Sage::

            sage: z = var('z')
            sage: maxima(gamma1(z)).sage()
            gamma(z)
            sage: latex(gamma1(z))
            \Gamma\left(z\right)

        Test that :trac:`5556` is fixed::

            sage: gamma1(3/4)
            gamma(3/4)

            sage: gamma1(3/4).n(100)
            1.2254167024651776451290983034

        Check that negative integer input works::

            sage: (-1).gamma()
            Infinity
            sage: (-1.).gamma()
            NaN
            sage: CC(-1).gamma()
            Infinity
            sage: RDF(-1).gamma()
            NaN
            sage: CDF(-1).gamma()
            Infinity

        Check if :trac:`8297` is fixed::

            sage: latex(gamma(1/4))
            \Gamma\left(\frac{1}{4}\right)

        Test pickling::

            sage: loads(dumps(gamma(x)))
            gamma(x)

        Check that the implementations roughly agrees (note there might be
        difference of several ulp on more complicated entries)::

            sage: import mpmath
            sage: float(gamma(10.)) == gamma(10.r) == float(gamma(mpmath.mpf(10)))
            True
            sage: float(gamma(8.5)) == gamma(8.5r) == float(gamma(mpmath.mpf(8.5)))
            True

        Check that ``QQbar`` half integers work with the ``pi`` formula::

            sage: gamma(QQbar(1/2))
            sqrt(pi)
            sage: gamma(QQbar(-9/2))
            -32/945*sqrt(pi)

        .. SEEALSO::

            :meth:`sage.functions.other.gamma`
        """
        GinacFunction.__init__(self, 'gamma', latex_name=r"\Gamma",
                               conversions={'mathematica':'Gamma',
                                            'maple':'GAMMA',
                                            'sympy':'gamma',
                                            'fricas':'Gamma',
                                            'giac':'Gamma'})

gamma1 = Function_gamma()

class Function_log_gamma(GinacFunction):
    def __init__(self):
        r"""
        The principal branch of the log gamma function. Note that for
        `x < 0`, ``log(gamma(x))`` is not, in general, equal to
        ``log_gamma(x)``.

        It is computed by the ``log_gamma`` function for the number type,
        or by ``lgamma`` in Ginac, failing that.

        Gamma is defined for complex input `z` with real part greater
        than zero, and by analytic continuation on the rest of the
        complex plane (except for negative integers, which are poles).

        EXAMPLES:

        Numerical evaluation happens when appropriate, to the
        appropriate accuracy (see :trac:`10072`)::

            sage: log_gamma(6)
            log(120)
            sage: log_gamma(6.)
            4.78749174278205
            sage: log_gamma(6).n()
            4.78749174278205
            sage: log_gamma(RealField(100)(6))
            4.7874917427820459942477009345
            sage: log_gamma(2.4 + I)
            -0.0308566579348816 + 0.693427705955790*I
            sage: log_gamma(-3.1)
            0.400311696703985 - 12.5663706143592*I
            sage: log_gamma(-1.1) == log(gamma(-1.1))
            False

        Symbolic input works (see :trac:`10075`)::

            sage: log_gamma(3*x)
            log_gamma(3*x)
            sage: log_gamma(3 + I)
            log_gamma(I + 3)
            sage: log_gamma(3 + I + x)
            log_gamma(x + I + 3)

        Check that :trac:`12521` is fixed::

            sage: log_gamma(-2.1)
            1.53171380819509 - 9.42477796076938*I
            sage: log_gamma(CC(-2.1))
            1.53171380819509 - 9.42477796076938*I
            sage: log_gamma(-21/10).n()
            1.53171380819509 - 9.42477796076938*I
            sage: exp(log_gamma(-1.3) + log_gamma(-0.4) -
            ....:     log_gamma(-1.3 - 0.4)).real_part()  # beta(-1.3, -0.4)
            -4.92909641669610

        In order to prevent evaluation, use the ``hold`` argument;
        to evaluate a held expression, use the ``n()`` numerical
        evaluation method::

            sage: log_gamma(SR(5), hold=True)
            log_gamma(5)
            sage: log_gamma(SR(5), hold=True).n()
            3.17805383034795

        TESTS::

            sage: log_gamma(-2.1 + I)
            -1.90373724496982 - 7.18482377077183*I
            sage: log_gamma(pari(6))
            4.78749174278205
            sage: log_gamma(x)._sympy_()
            loggamma(x)
            sage: log_gamma(CC(6))
            4.78749174278205
            sage: log_gamma(CC(-2.5))
            -0.0562437164976741 - 9.42477796076938*I
            sage: log_gamma(RDF(-2.5))
            -0.056243716497674054 - 9.42477796076938*I
            sage: log_gamma(CDF(-2.5))
            -0.056243716497674054 - 9.42477796076938*I
            sage: log_gamma(float(-2.5))
            (-0.056243716497674054-9.42477796076938j)
            sage: log_gamma(complex(-2.5))
            (-0.056243716497674054-9.42477796076938j)

        ``conjugate(log_gamma(x)) == log_gamma(conjugate(x))`` unless on the
        branch cut, which runs along the negative real axis.::

            sage: conjugate(log_gamma(x))
            conjugate(log_gamma(x))
            sage: var('y', domain='positive')
            y
            sage: conjugate(log_gamma(y))
            log_gamma(y)
            sage: conjugate(log_gamma(y + I))
            conjugate(log_gamma(y + I))
            sage: log_gamma(-2)
            +Infinity
            sage: conjugate(log_gamma(-2))
            +Infinity
        """
        GinacFunction.__init__(self, "log_gamma", latex_name=r'\log\Gamma',
                               conversions=dict(mathematica='LogGamma',
                                                maxima='log_gamma',
                                                sympy='loggamma',
                                                fricas='logGamma'))

log_gamma = Function_log_gamma()

class Function_gamma_inc(BuiltinFunction):
    def __init__(self):
        r"""
        The upper incomplete gamma function.

        It is defined by the integral

        .. MATH::

            \Gamma(a,z)=\int_z^\infty t^{a-1}e^{-t}\,\mathrm{d}t

        EXAMPLES::

            sage: gamma_inc(CDF(0,1), 3)
            0.0032085749933691158 + 0.012406185811871568*I
            sage: gamma_inc(RDF(1), 3)
            0.049787068367863944
            sage: gamma_inc(3,2)
            gamma(3, 2)
            sage: gamma_inc(x,0)
            gamma(x)
            sage: latex(gamma_inc(3,2))
            \Gamma\left(3, 2\right)
            sage: loads(dumps((gamma_inc(3,2))))
            gamma(3, 2)
            sage: i = ComplexField(30).0; gamma_inc(2, 1 + i)
            0.70709210 - 0.42035364*I
            sage: gamma_inc(2., 5)
            0.0404276819945128
            sage: x,y=var('x,y')
            sage: gamma_inc(x,y).diff(x)
            diff(gamma(x, y), x)
            sage: (gamma_inc(x,x+1).diff(x)).simplify()
            -(x + 1)^(x - 1)*e^(-x - 1) + D[0](gamma)(x, x + 1)

        TESTS:

        Check that :trac:`21407` is fixed::

            sage: gamma(-1,5)._sympy_()
            expint(2, 5)/5
            sage: gamma(-3/2,5)._sympy_()
            -6*sqrt(5)*exp(-5)/25 + 4*sqrt(pi)*erfc(sqrt(5))/3

    .. SEEALSO::

        :meth:`sage.functions.other.gamma`
        """
        BuiltinFunction.__init__(self, "gamma", nargs=2, latex_name=r"\Gamma",
                conversions={'maxima':'gamma_incomplete', 'mathematica':'Gamma',
                    'maple':'GAMMA', 'sympy':'uppergamma', 'giac':'ugamma'})

    def _eval_(self, x, y):
        """
        EXAMPLES::

            sage: gamma_inc(2.,0)
            1.00000000000000
            sage: gamma_inc(2,0)
            1
            sage: gamma_inc(1/2,2)
            -sqrt(pi)*(erf(sqrt(2)) - 1)
            sage: gamma_inc(1/2,1)
            -sqrt(pi)*(erf(1) - 1)
            sage: gamma_inc(1/2,0)
            sqrt(pi)
            sage: gamma_inc(x,0)
            gamma(x)
            sage: gamma_inc(1,2)
            e^(-2)
            sage: gamma_inc(0,2)
            -Ei(-2)
        """
        if y == 0:
            return gamma(x)
        if x == 1:
            return exp(-y)
        if x == 0:
            return -Ei(-y)
        if x == Rational(1)/2: #only for x>0
            from sage.functions.error import erf
            return sqrt(pi)*(1-erf(sqrt(y)))
        return None

    def _evalf_(self, x, y, parent=None, algorithm='pari'):
        """
        EXAMPLES::

            sage: gamma_inc(0,2)
            -Ei(-2)
            sage: gamma_inc(0,2.)
            0.0489005107080611
            sage: gamma_inc(0,2).n(algorithm='pari')
            0.0489005107080611
            sage: gamma_inc(0,2).n(200)
            0.048900510708061119567239835228...
            sage: gamma_inc(3,2).n()
            1.35335283236613

        TESTS:

        Check that :trac:`7099` is fixed::

            sage: R = RealField(1024)
            sage: gamma(R(9), R(10^-3))  # rel tol 1e-308
            40319.99999999999999999999999999988898884344822911869926361916294165058203634104838326009191542490601781777105678829520585311300510347676330951251563007679436243294653538925717144381702105700908686088851362675381239820118402497959018315224423868693918493033078310647199219674433536605771315869983788442389633
            sage: numerical_approx(gamma(9, 10^(-3)) - gamma(9), digits=40)  # abs tol 1e-36
            -1.110111598370794007949063502542063148294e-28

        Check that :trac:`17328` is fixed::

            sage: gamma_inc(float(-1), float(-1))
            (-0.8231640121031085+3.141592653589793j)
            sage: gamma_inc(RR(-1), RR(-1))
            -0.823164012103109 + 3.14159265358979*I
            sage: gamma_inc(-1, float(-log(3))) - gamma_inc(-1, float(-log(2)))  # abs tol 1e-15
            (1.2730972164471142+0j)

        Check that :trac:`17130` is fixed::

            sage: r = gamma_inc(float(0), float(1)); r
            0.21938393439552029
            sage: type(r)
            <... 'float'>
        """
        R = parent or s_parent(x)
        # C is the complex version of R
        # prec is the precision of R
        if R is float:
            prec = 53
            C = complex
        else:
            try:
                prec = R.precision()
            except AttributeError:
                prec = 53
            try:
                C = R.complex_field()
            except AttributeError:
                C = R

        if algorithm == 'pari':
            v = ComplexField(prec)(x).gamma_inc(y)
        else:
            import mpmath
            v = ComplexField(prec)(mpmath_utils.call(mpmath.gammainc, x, y, parent=R))
        if v.is_real():
            return R(v)
        else:
            return C(v)

# synonym.
gamma_inc = Function_gamma_inc()

class Function_gamma_inc_lower(BuiltinFunction):
    def __init__(self):
        r"""
        The lower incomplete gamma function.

        It is defined by the integral

        .. MATH::

            \Gamma(a,z)=\int_0^z t^{a-1}e^{-t}\,\mathrm{d}t

        EXAMPLES::

            sage: gamma_inc_lower(CDF(0,1), 3)
            -0.1581584032951798 - 0.5104218539302277*I
            sage: gamma_inc_lower(RDF(1), 3)
            0.950212931632136
            sage: gamma_inc_lower(3, 2, hold=True)
            gamma_inc_lower(3, 2)
            sage: gamma_inc_lower(3, 2)
            -10*e^(-2) + 2
            sage: gamma_inc_lower(x, 0)
            0
            sage: latex(gamma_inc_lower(x, x))
            \gamma\left(x, x\right)
            sage: loads(dumps((gamma_inc_lower(x, x))))
            gamma_inc_lower(x, x)
            sage: i = ComplexField(30).0; gamma_inc_lower(2, 1 + i)
            0.29290790 + 0.42035364*I
            sage: gamma_inc_lower(2., 5)
            0.959572318005487

        Interfaces to other software::

            sage: gamma_inc_lower(x,x)._sympy_()
            lowergamma(x, x)
            sage: maxima(gamma_inc_lower(x,x))
            gamma_greek(_SAGE_VAR_x,_SAGE_VAR_x)

    .. SEEALSO::

        :meth:`sage.functions.other.Function_gamma_inc`
        """
        BuiltinFunction.__init__(self, "gamma_inc_lower", nargs=2, latex_name=r"\gamma",
                conversions={'maxima':'gamma_greek', 'mathematica':'Gamma',
                    'maple':'GAMMA', 'sympy':'lowergamma', 'giac':'igamma'})

    def _eval_(self, x, y):
        """
        EXAMPLES::

            sage: gamma_inc_lower(2.,0)
            0.000000000000000
            sage: gamma_inc_lower(2,0)
            0
            sage: gamma_inc_lower(1/2,2)
            sqrt(pi)*erf(sqrt(2))
            sage: gamma_inc_lower(1/2,1)
            sqrt(pi)*erf(1)
            sage: gamma_inc_lower(1/2,0)
            0
            sage: gamma_inc_lower(x,0)
            0
            sage: gamma_inc_lower(1,2)
            -e^(-2) + 1
            sage: gamma_inc_lower(0,2)
            +Infinity
            sage: gamma_inc_lower(2,377/79)
            -456/79*e^(-377/79) + 1
            sage: gamma_inc_lower(3,x)
            -x^2*e^(-x) - 2*x*e^(-x) - 2*e^(-x) + 2
            sage: gamma_inc_lower(9/2,37/7)
            105/16*sqrt(pi)*erf(1/7*sqrt(259)) - 836473/19208*sqrt(259)*e^(-37/7)
        """
        if y == 0:
            return 0
        if x == 0:
            from sage.rings.infinity import Infinity
            return Infinity
        elif x == 1:
            return 1-exp(-y)
        elif (2*x).is_integer():
            return self(x,y,hold=True)._sympy_()
        else:
            return None

    def _evalf_(self, x, y, parent=None, algorithm='mpmath'):
        """
        EXAMPLES::

            sage: gamma_inc_lower(3,2.)
            0.646647167633873
            sage: gamma_inc_lower(3,2).n(200)
            0.646647167633873081060005050275155...
            sage: gamma_inc_lower(0,2.)
            +infinity
        """
        R = parent or s_parent(x)
        # C is the complex version of R
        # prec is the precision of R
        if R is float:
            prec = 53
            C = complex
        else:
            try:
                prec = R.precision()
            except AttributeError:
                prec = 53
            try:
                C = R.complex_field()
            except AttributeError:
                C = R
        if algorithm == 'pari':
            try:
                v = ComplexField(prec)(x).gamma() - ComplexField(prec)(x).gamma_inc(y)
            except AttributeError:
                if not (is_ComplexNumber(x)):
                    if is_ComplexNumber(y):
                        C = y.parent()
                    else:
                        C = ComplexField()
                        x = C(x)
            v = ComplexField(prec)(x).gamma() - ComplexField(prec)(x).gamma_inc(y)
        else:
            import mpmath
            v = ComplexField(prec)(mpmath_utils.call(mpmath.gammainc, x, 0, y, parent=R))
        if v.is_real():
            return R(v)
        else:
            return C(v)

    def _derivative_(self, x, y, diff_param=None):
        """
        EXAMPLES::

            sage: x,y = var('x,y')
            sage: gamma_inc_lower(x,y).diff(y)
            y^(x - 1)*e^(-y)
            sage: gamma_inc_lower(x,y).diff(x)
            Traceback (most recent call last):
            ...
            NotImplementedError: cannot differentiate gamma_inc_lower in the first parameter
        """
        if diff_param == 0:
            raise NotImplementedError("cannot differentiate gamma_inc_lower in the"
                                      " first parameter")
        else:
            return exp(-y)*y**(x - 1)

# synonym.
gamma_inc_lower = Function_gamma_inc_lower()

def gamma(a, *args, **kwds):
    r"""
    Gamma and upper incomplete gamma functions in one symbol.

    Recall that `\Gamma(n)` is `n-1` factorial::

        sage: gamma(11) == factorial(10)
        True
        sage: gamma(6)
        120
        sage: gamma(1/2)
        sqrt(pi)
        sage: gamma(-4/3)
        gamma(-4/3)
        sage: gamma(-1)
        Infinity
        sage: gamma(0)
        Infinity

    ::

        sage: gamma_inc(3,2)
        gamma(3, 2)
        sage: gamma_inc(x,0)
        gamma(x)

    ::

        sage: gamma(5, hold=True)
        gamma(5)
        sage: gamma(x, 0, hold=True)
        gamma(x, 0)

    ::

        sage: gamma(CDF(I))
        -0.15494982830181067 - 0.49801566811835607*I
        sage: gamma(CDF(0.5,14))
        -4.0537030780372815e-10 - 5.773299834553605e-10*I

    Use ``numerical_approx`` to get higher precision from
    symbolic expressions::

        sage: gamma(pi).n(100)
        2.2880377953400324179595889091
        sage: gamma(3/4).n(100)
        1.2254167024651776451290983034

    The precision for the result is also deduced from the precision of the
    input. Convert the input to a higher precision explicitly if a result
    with higher precision is desired.::

        sage: t = gamma(RealField(100)(2.5)); t
        1.3293403881791370204736256125
        sage: t.prec()
        100

    The gamma function only works with input that can be coerced to the
    Symbolic Ring::

        sage: Q.<i> = NumberField(x^2+1)
        sage: gamma(i)
        Traceback (most recent call last):
        ...
        TypeError: cannot coerce arguments: no canonical coercion from Number Field in i with defining polynomial x^2 + 1 to Symbolic Ring

    .. SEEALSO::

        :meth:`sage.functions.other.Function_gamma`
        """
    if not args:
        return gamma1(a, **kwds)
    if len(args) > 1:
        raise TypeError("Symbolic function gamma takes at most 2 arguments (%s given)"%(len(args)+1))
    return gamma_inc(a,args[0],**kwds)

def incomplete_gamma(*args, **kwds):
    """
        Deprecated name for :meth:`sage.functions.other.Function_gamma_inc`.

    TESTS::

        sage: incomplete_gamma(1,1)
        doctest:...: DeprecationWarning: Please use gamma_inc().
        See http://trac.sagemath.org/16697 for details.
        e^(-1)
    """
    from sage.misc.superseded import deprecation
    deprecation(16697, 'Please use gamma_inc().')
    return gamma_inc(*args, **kwds)

# We have to add the wrapper function manually to the symbol_table when we have
# two functions with different number of arguments and the same name
symbol_table['functions']['gamma'] = gamma

class Function_psi1(GinacFunction):
    def __init__(self):
        r"""
        The digamma function, `\psi(x)`, is the logarithmic derivative of the
        gamma function.

        .. MATH::

            \psi(x) = \frac{d}{dx} \log(\Gamma(x)) = \frac{\Gamma'(x)}{\Gamma(x)}

        EXAMPLES::

            sage: from sage.functions.other import psi1
            sage: psi1(x)
            psi(x)
            sage: psi1(x).derivative(x)
            psi(1, x)

        ::

            sage: psi1(3)
            -euler_gamma + 3/2

        ::

            sage: psi(.5)
            -1.96351002602142
            sage: psi(RealField(100)(.5))
            -1.9635100260214234794409763330

        TESTS::

            sage: latex(psi1(x))
            \psi\left(x\right)
            sage: loads(dumps(psi1(x)+1))
            psi(x) + 1

            sage: t = psi1(x); t
            psi(x)
            sage: t.subs(x=.2)
            -5.28903989659219
            sage: psi(x)._sympy_()
            polygamma(0, x)
        """
        GinacFunction.__init__(self, "psi", nargs=1, latex_name='\psi',
                               conversions=dict(mathematica='PolyGamma',
                                                maxima='psi[0]',
                                                sympy='digamma'))

class Function_psi2(GinacFunction):
    def __init__(self):
        r"""
        Derivatives of the digamma function `\psi(x)`. T

        EXAMPLES::

            sage: from sage.functions.other import psi2
            sage: psi2(2, x)
            psi(2, x)
            sage: psi2(2, x).derivative(x)
            psi(3, x)
            sage: n = var('n')
            sage: psi2(n, x).derivative(x)
            psi(n + 1, x)

        ::

            sage: psi2(0, x)
            psi(x)
            sage: psi2(-1, x)
            log(gamma(x))
            sage: psi2(3, 1)
            1/15*pi^4

        ::

            sage: psi2(2, .5).n()
            -16.8287966442343
            sage: psi2(2, .5).n(100)
            -16.828796644234319995596334261

        TESTS::

            sage: psi2(n, x).derivative(n)
            Traceback (most recent call last):
            ...
            RuntimeError: cannot diff psi(n,x) with respect to n

            sage: latex(psi2(2,x))
            \psi\left(2, x\right)
            sage: loads(dumps(psi2(2,x)+1))
            psi(2, x) + 1
            sage: psi(2, x)._sympy_()
            polygamma(2, x)
        """
        GinacFunction.__init__(self, "psi", nargs=2, latex_name='\psi',
                               conversions=dict(mathematica='PolyGamma',
                                                sympy='polygamma',
                                                giac='Psi'))

    def _maxima_init_evaled_(self, *args):
        """
        EXAMPLES:

        These are indirect doctests for this function.::

            sage: from sage.functions.other import psi2
            sage: psi2(2, x)._maxima_()
            psi[2](_SAGE_VAR_x)
            sage: psi2(4, x)._maxima_()
            psi[4](_SAGE_VAR_x)
        """
        args_maxima = []
        for a in args:
            if isinstance(a, str):
                args_maxima.append(a)
            elif hasattr(a, '_maxima_init_'):
                args_maxima.append(a._maxima_init_())
            else:
                args_maxima.append(str(a))
        n, x = args_maxima
        return "psi[%s](%s)"%(n, x)

psi1 = Function_psi1()
psi2 = Function_psi2()

def psi(x, *args, **kwds):
    r"""
    The digamma function, `\psi(x)`, is the logarithmic derivative of the
    gamma function.

    .. MATH::

        \psi(x) = \frac{d}{dx} \log(\Gamma(x)) = \frac{\Gamma'(x)}{\Gamma(x)}

    We represent the `n`-th derivative of the digamma function with
    `\psi(n, x)` or `psi(n, x)`.

    EXAMPLES::

        sage: psi(x)
        psi(x)
        sage: psi(.5)
        -1.96351002602142
        sage: psi(3)
        -euler_gamma + 3/2
        sage: psi(1, 5)
        1/6*pi^2 - 205/144
        sage: psi(1, x)
        psi(1, x)
        sage: psi(1, x).derivative(x)
        psi(2, x)

    ::

        sage: psi(3, hold=True)
        psi(3)
        sage: psi(1, 5, hold=True)
        psi(1, 5)

    TESTS::

        sage: psi(2, x, 3)
        Traceback (most recent call last):
        ...
        TypeError: Symbolic function psi takes at most 2 arguments (3 given)
    """
    if not args:
        return psi1(x, **kwds)
    if len(args) > 1:
        raise TypeError("Symbolic function psi takes at most 2 arguments (%s given)"%(len(args)+1))
    return psi2(x,args[0],**kwds)

# We have to add the wrapper function manually to the symbol_table when we have
# two functions with different number of arguments and the same name
symbol_table['functions']['psi'] = psi

def _swap_psi(a, b): return psi(b, a)
register_symbol(_swap_psi, {'giac':'Psi'})

class Function_factorial(GinacFunction):
    def __init__(self):
        r"""
        Returns the factorial of `n`.

        INPUT:

        -  ``n`` - any complex argument (except negative
           integers) or any symbolic expression


        OUTPUT: an integer or symbolic expression

        EXAMPLES::

            sage: x = var('x')
            sage: factorial(0)
            1
            sage: factorial(4)
            24
            sage: factorial(10)
            3628800
            sage: factorial(6) == 6*5*4*3*2
            True
            sage: f = factorial(x + factorial(x)); f
            factorial(x + factorial(x))
            sage: f(x=3)
            362880
            sage: factorial(x)^2
            factorial(x)^2

        To prevent automatic evaluation use the ``hold`` argument::

            sage: factorial(5,hold=True)
            factorial(5)

        To then evaluate again, we currently must use Maxima via
        :meth:`sage.symbolic.expression.Expression.simplify`::

            sage: factorial(5,hold=True).simplify()
            120

        We can also give input other than nonnegative integers.  For
        other nonnegative numbers, the :func:`gamma` function is used::

            sage: factorial(1/2)
            1/2*sqrt(pi)
            sage: factorial(3/4)
            gamma(7/4)
            sage: factorial(2.3)
            2.68343738195577

        But negative input always fails::

            sage: factorial(-32)
            Traceback (most recent call last):
            ...
            ValueError: factorial -- self = (-32) must be nonnegative

        TESTS:

        We verify that we can convert this function to Maxima and
        bring it back into Sage.::

            sage: z = var('z')
            sage: factorial._maxima_init_()
            'factorial'
            sage: maxima(factorial(z))
            factorial(_SAGE_VAR_z)
            sage: _.sage()
            factorial(z)
            sage: _._sympy_()
            factorial(z)
            sage: k = var('k')
            sage: factorial(k)
            factorial(k)

            sage: factorial(3.14)
            7.173269190187...

        Test latex typesetting::

            sage: latex(factorial(x))
            x!
            sage: latex(factorial(2*x))
            \left(2 \, x\right)!
            sage: latex(factorial(sin(x)))
            \sin\left(x\right)!
            sage: latex(factorial(sqrt(x+1)))
            \left(\sqrt{x + 1}\right)!
            sage: latex(factorial(sqrt(x)))
            \sqrt{x}!
            sage: latex(factorial(x^(2/3)))
            \left(x^{\frac{2}{3}}\right)!

            sage: latex(factorial)
            {\rm factorial}

        Check that :trac:`11539` is fixed::

            sage: (factorial(x) == 0).simplify()
            factorial(x) == 0
            sage: maxima(factorial(x) == 0).sage()
            factorial(x) == 0
            sage: y = var('y')
            sage: (factorial(x) == y).solve(x)
            [factorial(x) == y]

        Check that :trac:`16166` is fixed::

            sage: RBF=RealBallField(53)
            sage: factorial(RBF(4.2))
            [32.5780960503313 +/- 6.72e-14]

        Test pickling::

            sage: loads(dumps(factorial))
            factorial
        """
        GinacFunction.__init__(self, "factorial", latex_name='{\\rm factorial}',
                conversions=dict(maxima='factorial',
                                 mathematica='Factorial',
                                 sympy='factorial',
                                 fricas='factorial',
                                 giac='factorial'))

    def _eval_(self, x):
        """
        Evaluate the factorial function.

        Note that this method overrides the eval method defined in GiNaC
        which calls numeric evaluation on all numeric input. We preserve
        exact results if the input is a rational number.

        EXAMPLES::

            sage: k = var('k')
            sage: k.factorial()
            factorial(k)
            sage: SR(1/2).factorial()
            1/2*sqrt(pi)
            sage: SR(3/4).factorial()
            gamma(7/4)
            sage: SR(5).factorial()
            120
            sage: SR(3245908723049857203948572398475r).factorial()
            factorial(3245908723049857203948572398475L)
            sage: SR(3245908723049857203948572398475).factorial()
            factorial(3245908723049857203948572398475)
        """
        if isinstance(x, Rational):
            return gamma(x+1)
        elif isinstance(x, (Integer, int)) or self._is_numerical(x):
            return py_factorial_py(x)

        return None

factorial = Function_factorial()

class Function_binomial(GinacFunction):
    def __init__(self):
        r"""
        Return the binomial coefficient

        .. MATH::

            \binom{x}{m} = x (x-1) \cdots (x-m+1) / m!


        which is defined for `m \in \ZZ` and any
        `x`. We extend this definition to include cases when
        `x-m` is an integer but `m` is not by

        .. MATH::

            \binom{x}{m}= \binom{x}{x-m}

        If `m < 0`, return `0`.

        INPUT:

        -  ``x``, ``m`` - numbers or symbolic expressions. Either ``m``
           or ``x-m`` must be an integer, else the output is symbolic.

        OUTPUT: number or symbolic expression (if input is symbolic)

        EXAMPLES::

            sage: binomial(5,2)
            10
            sage: binomial(2,0)
            1
            sage: binomial(1/2, 0)
            1
            sage: binomial(3,-1)
            0
            sage: binomial(20,10)
            184756
            sage: binomial(-2, 5)
            -6
            sage: binomial(RealField()('2.5'), 2)
            1.87500000000000
            sage: n=var('n'); binomial(n,2)
            1/2*(n - 1)*n
            sage: n=var('n'); binomial(n,n)
            1
            sage: n=var('n'); binomial(n,n-1)
            n
            sage: binomial(2^100, 2^100)
            1

        ::

            sage: k, i = var('k,i')
            sage: binomial(k,i)
            binomial(k, i)

        We can use a ``hold`` parameter to prevent automatic evaluation::

            sage: SR(5).binomial(3, hold=True)
            binomial(5, 3)
            sage: SR(5).binomial(3, hold=True).simplify()
            10

        TESTS:

        We verify that we can convert this function to Maxima and
        bring it back into Sage.

        ::

            sage: n,k = var('n,k')
            sage: maxima(binomial(n,k))
            binomial(_SAGE_VAR_n,_SAGE_VAR_k)
            sage: _.sage()
            binomial(n, k)
            sage: _._sympy_()
            binomial(n, k)
            sage: binomial._maxima_init_()
            'binomial'

        For polynomials::

            sage: y = polygen(QQ, 'y')
            sage: binomial(y, 2).parent()
            Univariate Polynomial Ring in y over Rational Field

        Test pickling::

            sage: loads(dumps(binomial(n,k)))
            binomial(n, k)
        """
        GinacFunction.__init__(self, "binomial", nargs=2, preserved_arg=1,
                conversions=dict(maxima='binomial',
                                 mathematica='Binomial',
                                 sympy='binomial',
                                 fricas='binomial',
                                 giac='comb'))

    def _binomial_sym(self, n, k):
        """
        Expand the binomial formula symbolically when the second argument
        is an integer.

        EXAMPLES::

            sage: binomial._binomial_sym(x, 3)
            1/6*(x - 1)*(x - 2)*x
            sage: binomial._binomial_sym(x, x)
            Traceback (most recent call last):
            ...
            ValueError: second argument must be an integer
            sage: binomial._binomial_sym(x, SR(3))
            1/6*(x - 1)*(x - 2)*x

            sage: binomial._binomial_sym(x, 0r)
            1
            sage: binomial._binomial_sym(x, -1)
            0

            sage: y = polygen(QQ, 'y')
            sage: binomial._binomial_sym(y, 2).parent()
            Univariate Polynomial Ring in y over Rational Field
        """
        if isinstance(k, Expression):
            if k.is_integer():
                k = k.pyobject()
            else:
                raise ValueError("second argument must be an integer")

        if k < 0:
            return s_parent(k)(0)
        if k == 0:
            return s_parent(k)(1)
        if k == 1:
            return n

        from sage.misc.all import prod
        return prod(n - i for i in range(k)) / factorial(k)

    def _eval_(self, n, k):
        """
        EXAMPLES::

            sage: binomial._eval_(5, 3)
            10
            sage: type(binomial._eval_(5, 3))
            <type 'sage.rings.integer.Integer'>
            sage: type(binomial._eval_(5., 3))
            <type 'sage.rings.real_mpfr.RealNumber'>
            sage: binomial._eval_(x, 3)
            1/6*(x - 1)*(x - 2)*x
            sage: binomial._eval_(x, x-2)
            1/2*(x - 1)*x
            sage: n = var('n')
            sage: binomial._eval_(x, n) is None
            True

        TESTS::

            sage: y = polygen(QQ, 'y')
            sage: binomial._eval_(y, 2).parent()
            Univariate Polynomial Ring in y over Rational Field
        """
        if not isinstance(k, Expression):
            if not isinstance(n, Expression):
                n, k = coercion_model.canonical_coercion(n, k)
                return self._evalf_(n, k)
        if k in ZZ:
            return self._binomial_sym(n, k)
        if (n - k) in ZZ:
            return self._binomial_sym(n, n - k)

        return None

    def _evalf_(self, n, k, parent=None, algorithm=None):
        """
        EXAMPLES::

            sage: binomial._evalf_(5.r, 3)
            10.0
            sage: type(binomial._evalf_(5.r, 3))
            <... 'float'>
            sage: binomial._evalf_(1/2,1/1)
            1/2
            sage: binomial._evalf_(10^20+1/1,10^20)
            100000000000000000001
            sage: binomial._evalf_(SR(10**7),10**7)
            1
            sage: binomial._evalf_(3/2,SR(1/1))
            3/2
        """
        return arith_binomial(n, k)

binomial = Function_binomial()

class Function_beta(GinacFunction):
    def __init__(self):
        r"""
        Return the beta function.  This is defined by

        .. MATH::

            \operatorname{B}(p,q) = \int_0^1 t^{p-1}(1-t)^{q-1} dt

        for complex or symbolic input `p` and `q`.
        Note that the order of inputs does not matter:
        `\operatorname{B}(p,q)=\operatorname{B}(q,p)`.

        GiNaC is used to compute `\operatorname{B}(p,q)`.  However, complex inputs
        are not yet handled in general.  When GiNaC raises an error on
        such inputs, we raise a NotImplementedError.

        If either input is 1, GiNaC returns the reciprocal of the
        other.  In other cases, GiNaC uses one of the following
        formulas:

        .. MATH::

            \operatorname{B}(p,q) = \frac{\Gamma(p)\Gamma(q)}{\Gamma(p+q)}

        or

        .. MATH::

            \operatorname{B}(p,q) = (-1)^q \operatorname{B}(1-p-q, q).


        For numerical inputs, GiNaC uses the formula

        .. MATH::

            \operatorname{B}(p,q) =  \exp[\log\Gamma(p)+\log\Gamma(q)-\log\Gamma(p+q)]


        INPUT:

        -  ``p`` - number or symbolic expression

        -  ``q`` - number or symbolic expression


        OUTPUT: number or symbolic expression (if input is symbolic)

        EXAMPLES::

            sage: beta(3,2)
            1/12
            sage: beta(3,1)
            1/3
            sage: beta(1/2,1/2)
            beta(1/2, 1/2)
            sage: beta(-1,1)
            -1
            sage: beta(-1/2,-1/2)
            0
            sage: ex = beta(x/2,3)
            sage: set(ex.operands()) == set([1/2*x, 3])
            True
            sage: beta(.5,.5)
            3.14159265358979
            sage: beta(1,2.0+I)
            0.400000000000000 - 0.200000000000000*I
            sage: ex = beta(3,x+I)
            sage: set(ex.operands()) == set([x+I, 3])
            True

        The result is symbolic if exact input is given::

            sage: ex = beta(2,1+5*I); ex
            beta(...
            sage: set(ex.operands()) == set([1+5*I, 2])
            True
            sage: beta(2, 2.)
            0.166666666666667
            sage: beta(I, 2.)
            -0.500000000000000 - 0.500000000000000*I
            sage: beta(2., 2)
            0.166666666666667
            sage: beta(2., I)
            -0.500000000000000 - 0.500000000000000*I

            sage: beta(x, x)._sympy_()
            beta(x, x)

        Test pickling::

            sage: loads(dumps(beta))
            beta

        Check that :trac:`15196` is fixed::

            sage: beta(-1.3,-0.4)
            -4.92909641669610
        """
        GinacFunction.__init__(self, 'beta', nargs=2,
                               latex_name=r"\operatorname{B}",
                               conversions=dict(maxima='beta',
                                                mathematica='Beta',
                                                sympy='beta',
                                                fricas='Beta',
                                                giac='Beta'))

beta = Function_beta()

def _do_sqrt(x, prec=None, extend=True, all=False):
        r"""
        Used internally to compute the square root of x.

        INPUT:

        -  ``x`` - a number

        -  ``prec`` - None (default) or a positive integer
           (bits of precision) If not None, then compute the square root
           numerically to prec bits of precision.

        -  ``extend`` - bool (default: True); this is a place
           holder, and is always ignored since in the symbolic ring everything
           has a square root.

        -  ``extend`` - bool (default: True); whether to extend
           the base ring to find roots. The extend parameter is ignored if
           prec is a positive integer.

        -  ``all`` - bool (default: False); whether to return
           a list of all the square roots of x.


        EXAMPLES::

            sage: from sage.functions.other import _do_sqrt
            sage: _do_sqrt(3)
            sqrt(3)
            sage: _do_sqrt(3,prec=10)
            1.7
            sage: _do_sqrt(3,prec=100)
            1.7320508075688772935274463415
            sage: _do_sqrt(3,all=True)
            [sqrt(3), -sqrt(3)]

        Note that the extend parameter is ignored in the symbolic ring::

            sage: _do_sqrt(3,extend=False)
            sqrt(3)
        """
        if prec:
            if x >= 0:
                 return RealField(prec)(x).sqrt(all=all)
            else:
                 return ComplexField(prec)(x).sqrt(all=all)
        if x == -1:
            z = I
        else:
            z = SR(x) ** one_half

        if all:
            if z:
                return [z, -z]
            else:
                return [z]
        return z

def sqrt(x, *args, **kwds):
        r"""
        INPUT:

        -  ``x`` - a number

        -  ``prec`` - integer (default: None): if None, returns
           an exact square root; otherwise returns a numerical square root if
           necessary, to the given bits of precision.

        -  ``extend`` - bool (default: True); this is a place
           holder, and is always ignored or passed to the sqrt function for x,
           since in the symbolic ring everything has a square root.

        -  ``all`` - bool (default: False); if True, return all
           square roots of self, instead of just one.

        EXAMPLES::

            sage: sqrt(-1)
            I
            sage: sqrt(2)
            sqrt(2)
            sage: sqrt(2)^2
            2
            sage: sqrt(4)
            2
            sage: sqrt(4,all=True)
            [2, -2]
            sage: sqrt(x^2)
            sqrt(x^2)

        For a non-symbolic square root, there are a few options.
        The best is to numerically approximate afterward::

            sage: sqrt(2).n()
            1.41421356237310
            sage: sqrt(2).n(prec=100)
            1.4142135623730950488016887242

        Or one can input a numerical type.

            sage: sqrt(2.)
            1.41421356237310
            sage: sqrt(2.000000000000000000000000)
            1.41421356237309504880169
            sage: sqrt(4.0)
            2.00000000000000

        To prevent automatic evaluation, one can use the ``hold`` parameter
        after coercing to the symbolic ring::

            sage: sqrt(SR(4),hold=True)
            sqrt(4)
            sage: sqrt(4,hold=True)
            Traceback (most recent call last):
            ...
            TypeError: _do_sqrt() got an unexpected keyword argument 'hold'

        This illustrates that the bug reported in :trac:`6171` has been fixed::

            sage: a = 1.1
            sage: a.sqrt(prec=100)  # this is supposed to fail
            Traceback (most recent call last):
            ...
            TypeError: sqrt() got an unexpected keyword argument 'prec'
            sage: sqrt(a, prec=100)
            1.0488088481701515469914535137
            sage: sqrt(4.00, prec=250)
            2.0000000000000000000000000000000000000000000000000000000000000000000000000

        One can use numpy input as well::

            sage: import numpy
            sage: a = numpy.arange(2,5)
            sage: sqrt(a)
            array([ 1.41421356,  1.73205081,  2.        ])
        """
        if isinstance(x, float):
            return math.sqrt(x)
        elif type(x).__module__ == 'numpy':
            from numpy import sqrt
            return sqrt(x)
        try:
            return x.sqrt(*args, **kwds)
        # The following includes TypeError to catch cases where sqrt
        # is called with a "prec" keyword, for example, but the sqrt
        # method for x doesn't accept such a keyword.
        except (AttributeError, TypeError):
            pass
        return _do_sqrt(x, *args, **kwds)

# register sqrt in pynac symbol_table for conversion back from other systems
register_symbol(sqrt, dict(mathematica='Sqrt'))
symbol_table['functions']['sqrt'] = sqrt

Function_sqrt = type('deprecated_sqrt', (),
        {'__call__': staticmethod(sqrt),
            '__setstate__': lambda x, y: None})

class Function_arg(BuiltinFunction):
    def __init__(self):
        r"""
        The argument function for complex numbers.

        EXAMPLES::

            sage: arg(3+i)
            arctan(1/3)
            sage: arg(-1+i)
            3/4*pi
            sage: arg(2+2*i)
            1/4*pi
            sage: arg(2+x)
            arg(x + 2)
            sage: arg(2.0+i+x)
            arg(x + 2.00000000000000 + 1.00000000000000*I)
            sage: arg(-3)
            pi
            sage: arg(3)
            0
            sage: arg(0)
            0

            sage: latex(arg(x))
            {\rm arg}\left(x\right)
            sage: maxima(arg(x))
            atan2(0,_SAGE_VAR_x)
            sage: maxima(arg(2+i))
            atan(1/2)
            sage: maxima(arg(sqrt(2)+i))
            atan(1/sqrt(2))
            sage: arg(x)._sympy_()
            arg(x)

            sage: arg(2+i)
            arctan(1/2)
            sage: arg(sqrt(2)+i)
            arg(sqrt(2) + I)
            sage: arg(sqrt(2)+i).simplify()
            arctan(1/2*sqrt(2))

        TESTS::

            sage: arg(0.0)
            0.000000000000000
            sage: arg(3.0)
            0.000000000000000
            sage: arg(-2.5)
            3.14159265358979
            sage: arg(2.0+3*i)
            0.982793723247329
        """
        BuiltinFunction.__init__(self, "arg",
                conversions=dict(maxima='carg',
                                 mathematica='Arg',
                                 sympy='arg',
                                 giac='arg'))

    def _eval_(self, x):
        """
        EXAMPLES::

            sage: arg(3+i)
            arctan(1/3)
            sage: arg(-1+i)
            3/4*pi
            sage: arg(2+2*i)
            1/4*pi
            sage: arg(2+x)
            arg(x + 2)
            sage: arg(2.0+i+x)
            arg(x + 2.00000000000000 + 1.00000000000000*I)
            sage: arg(-3)
            pi
            sage: arg(3)
            0
            sage: arg(0)
            0
            sage: arg(sqrt(2)+i)
            arg(sqrt(2) + I)

        """
        if isinstance(x,Expression):
            if x.is_trivial_zero():
                return x
        else:
            if not x:
                return x
            else:
                return arctan2(imag_part(x),real_part(x))

    def _evalf_(self, x, parent=None, algorithm=None):
        """
        EXAMPLES::

            sage: arg(0.0)
            0.000000000000000
            sage: arg(3.0)
            0.000000000000000
            sage: arg(3.00000000000000000000000000)
            0.00000000000000000000000000
            sage: arg(3.00000000000000000000000000).prec()
            90
            sage: arg(ComplexIntervalField(90)(3)).prec()
            90
            sage: arg(ComplexIntervalField(90)(3)).parent()
            Real Interval Field with 90 bits of precision
            sage: arg(3.0r)
            0.0
            sage: arg(RDF(3))
            0.0
            sage: arg(RDF(3)).parent()
            Real Double Field
            sage: arg(-2.5)
            3.14159265358979
            sage: arg(2.0+3*i)
            0.982793723247329

        TESTS:

        Make sure that the ``_evalf_`` method works when it receives a
        keyword argument ``parent`` :trac:`12289`::

            sage: arg(5+I, hold=True).n()
            0.197395559849881
        """
        try:
            return x.arg()
        except AttributeError:
            pass
        # try to find a parent that support .arg()
        if parent is None:
            parent = s_parent(x)
        try:
            parent = parent.complex_field()
        except AttributeError:
            try:
                parent = ComplexField(x.prec())
            except AttributeError:
                parent = ComplexField()

        return parent(x).arg()

arg=Function_arg()


############################
# Real and Imaginary Parts #
############################
class Function_real_part(GinacFunction):
    def __init__(self):
        r"""
        Returns the real part of the (possibly complex) input.

        It is possible to prevent automatic evaluation using the
        ``hold`` parameter::

            sage: real_part(I,hold=True)
            real_part(I)

        To then evaluate again, we currently must use Maxima via
        :meth:`sage.symbolic.expression.Expression.simplify`::

            sage: real_part(I,hold=True).simplify()
            0

        EXAMPLES::

            sage: z = 1+2*I
            sage: real(z)
            1
            sage: real(5/3)
            5/3
            sage: a = 2.5
            sage: real(a)
            2.50000000000000
            sage: type(real(a))
            <type 'sage.rings.real_mpfr.RealLiteral'>
            sage: real(1.0r)
            1.0
            sage: real(complex(3, 4))
            3.0

        Sage can recognize some expressions as real and accordingly
        return the identical argument::

            sage: SR.var('x', domain='integer').real_part()
            x
            sage: SR.var('x', domain='integer').imag_part()
            0
            sage: real_part(sin(x)+x)
            x + sin(x)
            sage: real_part(x*exp(x))
            x*e^x
            sage: imag_part(sin(x)+x)
            0
            sage: real_part(real_part(x))
            x
            sage: forget()

        TESTS::

            sage: loads(dumps(real_part))
            real_part
            sage: real_part(x)._sympy_()
            re(x)

        Check if :trac:`6401` is fixed::

            sage: latex(x.real())
            \Re \left( x \right)

            sage: f(x) = function('f')(x)
            sage: latex( f(x).real())
            \Re \left( f\left(x\right) \right)

        Check that some real part expansions evaluate correctly
        (:trac:`21614`)::

            sage: real(sqrt(sin(x))).subs(x==0)
            0
        """
        GinacFunction.__init__(self, "real_part",
                               conversions=dict(maxima='realpart',
                                                sympy='re',
                                                giac='re'),
                               alt_name="real")

    def __call__(self, x, **kwargs):
        r"""
        TESTS::

            sage: type(real(complex(3, 4)))
            <... 'float'>
        """
        if isinstance(x, complex):
            return x.real
        else:
            return GinacFunction.__call__(self, x, **kwargs)

real = real_part = Function_real_part()

class Function_imag_part(GinacFunction):
    def __init__(self):
        r"""
        Returns the imaginary part of the (possibly complex) input.

        It is possible to prevent automatic evaluation using the
        ``hold`` parameter::

            sage: imag_part(I,hold=True)
            imag_part(I)

        To then evaluate again, we currently must use Maxima via
        :meth:`sage.symbolic.expression.Expression.simplify`::

            sage: imag_part(I,hold=True).simplify()
            1

        TESTS::

            sage: z = 1+2*I
            sage: imaginary(z)
            2
            sage: imag(z)
            2
            sage: imag(complex(3, 4))
            4.0
            sage: loads(dumps(imag_part))
            imag_part
            sage: imag_part(x)._sympy_()
            im(x)

        Check if :trac:`6401` is fixed::

            sage: latex(x.imag())
            \Im \left( x \right)

            sage: f(x) = function('f')(x)
            sage: latex( f(x).imag())
            \Im \left( f\left(x\right) \right)
        """
        GinacFunction.__init__(self, "imag_part",
                               conversions=dict(maxima='imagpart',
                                                sympy='im',
                                                giac='im'),
                               alt_name="imag")

    def __call__(self, x, **kwargs):
        r"""
        TESTS::

            sage: type(imag(complex(3, 4)))
            <... 'float'>
        """
        if isinstance(x, complex):
            return x.imag
        else:
            return GinacFunction.__call__(self, x, **kwargs)

imag = imag_part = imaginary = Function_imag_part()


############################
# Complex Conjugate        #
############################
class Function_conjugate(GinacFunction):
    def __init__(self):
        r"""
        Returns the complex conjugate of the input.

        It is possible to prevent automatic evaluation using the
        ``hold`` parameter::

            sage: conjugate(I,hold=True)
            conjugate(I)

        To then evaluate again, we currently must use Maxima via
        :meth:`sage.symbolic.expression.Expression.simplify`::

            sage: conjugate(I,hold=True).simplify()
            -I

        TESTS::

            sage: x,y = var('x,y')
            sage: x.conjugate()
            conjugate(x)
            sage: _._sympy_()
            conjugate(x)
            sage: latex(conjugate(x))
            \overline{x}
            sage: f = function('f')
            sage: latex(f(x).conjugate())
            \overline{f\left(x\right)}
            sage: f = function('psi')(x,y)
            sage: latex(f.conjugate())
            \overline{\psi\left(x, y\right)}
            sage: x.conjugate().conjugate()
            x
            sage: x.conjugate().operator()
            conjugate
            sage: x.conjugate().operator() == conjugate
            True

        Check if :trac:`8755` is fixed::

            sage: conjugate(sqrt(-3))
            conjugate(sqrt(-3))
            sage: conjugate(sqrt(3))
            sqrt(3)
            sage: conjugate(sqrt(x))
            conjugate(sqrt(x))
            sage: conjugate(x^2)
            conjugate(x)^2
            sage: var('y',domain='positive')
            y
            sage: conjugate(sqrt(y))
            sqrt(y)

        Check if :trac:`10964` is fixed::

            sage: z= I*sqrt(-3); z
            I*sqrt(-3)
            sage: conjugate(z)
            -I*conjugate(sqrt(-3))
            sage: var('a')
            a
            sage: conjugate(a*sqrt(-2)*sqrt(-3))
            conjugate(sqrt(-2))*conjugate(sqrt(-3))*conjugate(a)

        Check that sums are handled correctly::

            sage: y = var('y', domain='real')
            sage: conjugate(y + I)
            y - I

        Test pickling::

            sage: loads(dumps(conjugate))
            conjugate
        """
        GinacFunction.__init__(self, "conjugate",
                               conversions=dict(sympy='conjugate',
                                                giac='conj'))

conjugate = Function_conjugate()


class Function_sum(BuiltinFunction):
    """
    Placeholder symbolic sum function that is only accessible internally.

    EXAMPLES::

        sage: from sage.functions.other import symbolic_sum as ssum
        sage: r = ssum(x, x, 1, 10); r
        sum(x, x, 1, 10)
        sage: r.unhold()
        55
    """
    def __init__(self):
        """
        EXAMPLES::

            sage: from sage.functions.other import symbolic_sum as ssum
            sage: maxima(ssum(x, x, 1, 10))
            55
        """
        BuiltinFunction.__init__(self, "sum", nargs=4,
                               conversions=dict(maxima='sum'))

    def _print_latex_(self, x, var, a, b):
        r"""
        EXAMPLES::

            sage: from sage.functions.other import symbolic_sum as ssum
            sage: latex(ssum(x^2, x, 1, 10))
            {\sum_{x=1}^{10} x^{2}}
        """
        return r"{{\sum_{{{}={}}}^{{{}}} {}}}".format(latex(var), latex(a),
                                                      latex(b), latex(x))

symbolic_sum = Function_sum()


class Function_prod(BuiltinFunction):
    """
    Placeholder symbolic product function that is only accessible internally.

    EXAMPLES::

        sage: from sage.functions.other import symbolic_product as sprod
        sage: r = sprod(x, x, 1, 10); r
        product(x, x, 1, 10)
        sage: r.unhold()
        3628800
    """
    def __init__(self):
        """
        EXAMPLES::

            sage: from sage.functions.other import symbolic_product as sprod
            sage: _ = var('m n', domain='integer')
            sage: r = maxima(sprod(sin(m), m, 1, n)).sage(); r
            product(sin(m), m, 1, n)
            sage: isinstance(r.operator(), sage.functions.other.Function_prod)
            True
            sage: r = sympy(sprod(sin(m), m, 1, n)).sage(); r # known bug
            product(sin(m), m, 1, n)
            sage: isinstance(r.operator(),
            ....:     sage.functions.other.Function_prod) # known bug
            True
            sage: giac(sprod(m, m, 1, n))
            n!
        """
        BuiltinFunction.__init__(self, "product", nargs=4,
                               conversions=dict(maxima='product',
                                   sympy='Product', giac='product'))

    def _print_latex_(self, x, var, a, b):
        r"""
        EXAMPLES::

            sage: from sage.functions.other import symbolic_product as sprod
            sage: latex(sprod(x^2, x, 1, 10))
            {\prod_{x=1}^{10} x^{2}}
        """
        return r"{{\prod_{{{}={}}}^{{{}}} {}}}".format(latex(var), latex(a),
                                                       latex(b), latex(x))

symbolic_product = Function_prod()


class Function_limit(BuiltinFunction):
    """
    Placeholder symbolic limit function that is only accessible internally.

    This function is called to create formal wrappers of limits that
    Maxima can't compute::

        sage: a = lim(exp(x^2)*(1-erf(x)), x=infinity); a
        -limit((erf(x) - 1)*e^(x^2), x, +Infinity)

    EXAMPLES::

        sage: from sage.functions.other import symbolic_limit as slimit
        sage: slimit(1/x, x, +oo)
        limit(1/x, x, +Infinity)
        sage: var('minus,plus')
        (minus, plus)
        sage: slimit(1/x, x, +oo)
        limit(1/x, x, +Infinity)
        sage: slimit(1/x, x, 0, plus)
        limit(1/x, x, 0, plus)
        sage: slimit(1/x, x, 0, minus)
        limit(1/x, x, 0, minus)
    """
    def __init__(self):
        """
        EXAMPLES::

            sage: from sage.functions.other import symbolic_limit as slimit
            sage: maxima(slimit(1/x, x, +oo))
            0
        """
        BuiltinFunction.__init__(self, "limit", nargs=0,
                               conversions=dict(maxima='limit'))

    def _latex_(self):
        r"""
        EXAMPLES::

            sage: from sage.functions.other import symbolic_limit as slimit
            sage: latex(slimit)
            \lim
        """
        return r'\lim'

    def _print_latex_(self, ex, var, to, direction=''):
        r"""
        EXAMPLES::

            sage: from sage.functions.other import symbolic_limit as slimit
            sage: var('x,a')
            (x, a)
            sage: f = function('f')
            sage: latex(slimit(f(x), x, a))
            \lim_{x \to a}\, f\left(x\right)
            sage: latex(limit(f(x), x=oo))
            \lim_{x \to +\infty}\, f\left(x\right)

        TESTS:

        When one-sided limits are converted back from maxima, the direction
        argument becomes a symbolic variable. We check if typesetting these works::

            sage: from sage.functions.other import symbolic_limit as slimit
            sage: var('minus,plus')
            (minus, plus)
            sage: latex(slimit(f(x), x, a, minus))
            \lim_{x \to a^-}\, f\left(x\right)
            sage: latex(slimit(f(x), x, a, plus))
            \lim_{x \to a^+}\, f\left(x\right)
            sage: latex(limit(f(x),x=a,dir='+'))
            \lim_{x \to a^+}\, f\left(x\right)
            sage: latex(limit(f(x),x=a,dir='right'))
            \lim_{x \to a^+}\, f\left(x\right)
            sage: latex(limit(f(x),x=a,dir='-'))
            \lim_{x \to a^-}\, f\left(x\right)
            sage: latex(limit(f(x),x=a,dir='left'))
            \lim_{x \to a^-}\, f\left(x\right)

        Check if :trac:`13181` is fixed::

            sage: t = var('t')
            sage: latex(limit(exp_integral_e(1/2, I*t - I*x)*sqrt(-t + x),t=x,dir='-'))
            \lim_{t \to x^-}\, \sqrt{-t + x} exp_integral_e\left(\frac{1}{2}, i \, t - i \, x\right)
            sage: latex(limit(exp_integral_e(1/2, I*t - I*x)*sqrt(-t + x),t=x,dir='+'))
            \lim_{t \to x^+}\, \sqrt{-t + x} exp_integral_e\left(\frac{1}{2}, i \, t - i \, x\right)
            sage: latex(limit(exp_integral_e(1/2, I*t - I*x)*sqrt(-t + x),t=x))
            \lim_{t \to x}\, \sqrt{-t + x} exp_integral_e\left(\frac{1}{2}, i \, t - i \, x\right)
        """
        if repr(direction) == 'minus':
            dir_str = '^-'
        elif repr(direction) == 'plus':
            dir_str = '^+'
        else:
            dir_str = ''
        return r"\lim_{{{} \to {}{}}}\, {}".format(latex(var),
                latex(to), dir_str, latex(ex))

symbolic_limit = Function_limit()


class Function_cases(GinacFunction):
    """
    Formal function holding ``(condition, expression)`` pairs.

    Numbers are considered conditions with zero being ``False``.
    A true condition marks a default value. The function is not
    evaluated as long as it contains a relation that cannot be
    decided by Pynac.

    EXAMPLES::

        sage: ex = cases([(x==0, pi), (True, 0)]); ex
        cases(((x == 0, pi), (1, 0)))
        sage: ex.subs(x==0)
        pi
        sage: ex.subs(x==2)
        0
        sage: ex + 1
        cases(((x == 0, pi), (1, 0))) + 1
        sage: _.subs(x==0)
        pi + 1

    The first encountered default is used, as well as the first relation
    that can be trivially decided::

        sage: cases(((True, pi), (True, 0)))
        pi

        sage: _ = var('y')
        sage: ex = cases(((x==0, pi), (y==1, 0))); ex
        cases(((x == 0, pi), (y == 1, 0)))
        sage: ex.subs(x==0)
        pi
        sage: ex.subs(x==0, y==1)
        pi
    """
    def __init__(self):
        """
        EXAMPLES::

            sage: loads(dumps(cases))
            cases
        """
        GinacFunction.__init__(self, "cases")

    def __call__(self, l, **kwargs):
        """
        EXAMPLES::

            sage: ex = cases([(x==0, pi), (True, 0)]); ex
            cases(((x == 0, pi), (1, 0)))

        TESTS::

            sage: cases()
            Traceback (most recent call last):
            ...
            TypeError: __call__() takes exactly 2 arguments (1 given)
            
            sage: cases(x)
            Traceback (most recent call last):
            ...
            RuntimeError: cases argument not a sequence
        """
        return GinacFunction.__call__(self,
                SR._force_pyobject(l), **kwargs)

    def _print_latex_(self, l, **kwargs):
        r"""
        EXAMPLES::

            sage: ex = cases([(x==0, pi), (True, 0)]); ex
            cases(((x == 0, pi), (1, 0)))
            sage: latex(ex)
            \begin{cases}{\pi} & {x = 0}\\{0} & {1}\end{cases}
        """
        if not isinstance(l, (list, tuple)):
            raise ValueError("cases() argument must be a list")
        str = r"\begin{cases}"
        for pair in l:
            left = None
            if (isinstance(pair, tuple)):
                right,left = pair
            else:
                right = pair
            str += r"{%s} & {%s}\\" % (latex(left), latex(right))
        print(str[:-2] + r"\end{cases}")

    def _sympy_(self, l):
        """
        Convert this cases expression to its SymPy equivalent.

        EXAMPLES::

            sage: ex = cases(((x<0, pi), (x==1, 1), (True, 0)))
            sage: assert ex == ex._sympy_()._sage_()
        """
        from sage.symbolic.ring import SR
        from sympy import Piecewise as pw
        args = []
        for tup in l.operands():
            cond,expr = tup.operands()
            if SR(cond).is_numeric():
                args.append((SR(expr)._sympy_(), bool(SR(cond)._sympy_())))
            else:
                args.append((SR(expr)._sympy_(), SR(cond)._sympy_()))
        return pw(*args)

cases = Function_cases()


class Function_crootof(BuiltinFunction):
    """
    Formal function holding ``(polynomial, index)`` pairs.

    The expression evaluates to a floating point value that is an
    approximation to a specific complex root of the polynomial. The
    ordering is fixed so you always get the same root.

    The functionality is imported from SymPy, see
    http://docs.sympy.org/latest/_modules/sympy/polys/rootoftools.html

    EXAMPLES::

        sage: c = complex_root_of(x^6 + x + 1, 1); c
        complex_root_of(x^6 + x + 1, 1)
        sage: c.n()
        -0.790667188814418 + 0.300506920309552*I
        sage: c.n(100)
        -0.79066718881441764449859281847 + 0.30050692030955162512001002521*I
        sage: (c^6 + c + 1).n(100) < 1e-25
        True
    """
    def __init__(self):
        """
        EXAMPLES::

            sage: loads(dumps(complex_root_of))
            complex_root_of
        """
        BuiltinFunction.__init__(self, "complex_root_of", nargs=2,
                                   conversions=dict(sympy='CRootOf'),
                                   evalf_params_first=False)

    def _eval_(self, poly, index):
        """
        TESTS::

            sage: _ = var('y')
            sage: complex_root_of(1, 1)
            Traceback (most recent call last):
            ...
            ValueError: polynomial in one variable required
            sage: complex_root_of(x+y, 1)
            Traceback (most recent call last):
            ...
            ValueError: polynomial in one variable required
            sage: complex_root_of(sin(x), 1)
            Traceback (most recent call last):
            ...
            ValueError: polynomial in one variable required
        """
        try:
            vars = poly.variables()
        except AttributeError:
            raise ValueError('polynomial in one variable required')
        if len(vars) != 1 or not poly.is_polynomial(vars[0]):
            raise ValueError('polynomial in one variable required')

    def _evalf_(self, poly, index, parent=None, algorithm=None):
        """
        EXAMPLES::

            sage: complex_root_of(x^2-2, 1).n()
            1.41421356237309
            sage: complex_root_of(x^2-2, 3).n()
            Traceback (most recent call last):
            ...
            IndexError: root index out of [-2, 1] range, got 3

        TESTS:

        Check that low precision is handled (:trac:`24378`)::

            sage: complex_root_of(x^8-1, 7).n(2)
            0.75 + 0.75*I
            sage: complex_root_of(x^8-1, 7).n(20)
            0.70711 + 0.70711*I
        """
        from sympy.core.evalf import prec_to_dps
        from sympy.polys import CRootOf, Poly
        try:
            prec = parent.precision()
        except AttributeError:
            prec = 53
        sobj = CRootOf(Poly(poly._sympy_()), int(index))
        return parent(sobj.n(1 + prec_to_dps(prec))._sage_())

complex_root_of = Function_crootof()

