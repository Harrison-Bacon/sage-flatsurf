#*****************************************************************************
#       Copyright (C) 2013-2019 Vincent Delecroix <20100.delecroix@gmail.com>
#                     2013-2019 W. Patrick Hooper <wphooper@gmail.com>
#
#  Distributed under the terms of the GNU General Public License (GPL)
#  as published by the Free Software Foundation; either version 2 of
#  the License, or (at your option) any later version.
#                  https://www.gnu.org/licenses/
#*****************************************************************************

from __future__ import absolute_import, print_function, division
from six.moves import range, map, filter, zip

from flatsurf.geometry.half_dilation_surface import HalfDilationSurface

from six import iteritems
from sage.matrix.constructor import identity_matrix
from .surface import Surface
from .half_translation_surface import HalfTranslationSurface
from .polygon import ConvexPolygons, wedge_product, triangulate, build_faces

from sage.misc.cachefunc import cached_method
from sage.misc.sage_unittest import TestSuite

from sage.structure.sage_object import SageObject

from sage.rings.infinity import Infinity

from sage.rings.all import ZZ, QQ, AA, RIF, RR, NumberField

from sage.modules.free_module_element import vector

from sage.matrix.constructor import matrix, identity_matrix
from sage.modules.free_module import VectorSpace

from .matrix_2x2 import (is_similarity,
                    homothety_rotation_decomposition,
                    similarity_from_vectors,
                    rotation_matrix_angle,
                    is_cosine_sine_of_rational)

from .similarity import SimilarityGroup
from .polygon import ConvexPolygons, wedge_product, triangulate, build_faces

from .surface import Surface, Surface_dict, Surface_list, LabelComparator
from .surface_objects import Singularity, SaddleConnection, SurfacePoint
from .circle import Circle





class DilationSurface(HalfDilationSurface):
    r"""
    Dilation surface.

    A dilation surface is a (G,X) structure on a surface for the group
    of positive dilatations `G = \RR_+` acting on the plane `X = \RR^2`.
    """

    def canonicalize(self, in_place=False, group = "dilation"):
        return super(DilationSurface, self).canonicalize(group = group)