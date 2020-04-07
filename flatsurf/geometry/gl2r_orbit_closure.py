r"""
GL(2,R)-orbit closure of translation surfaces

.. TODO::

    - Comparison of renf_elem with Python int not supported (but seem to work
      through the RealEmbeddedNumberField)

    - the method name ``fromEdge`` is completely misleading
      (how do we guess that it build a vector, how do we guess that it takes a half-edge as input)

    - Theorem 1.9 of Alex Wright: the field of definition is contained in the field generated by
      the ratio of circumferences. We should provide a method, .reset_field_of_definition or
      something similar
"""
######################################################################
#  This file is part of sage-flatsurf.
#
#        Copyright (C) 2019-2020 Julian Rüth
#                      2020      Vincent Delecroix
#
#  sage-flatsurf is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 2 of the License, or
#  (at your option) any later version.
#
#  sage-flatsurf is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with sage-flatsurf. If not, see <https://www.gnu.org/licenses/>.
######################################################################

import cppyy
from pyeantic import RealEmbeddedNumberField

import pyflatsurf
import pyflatsurf.vector

# TODO: move into flatsurf
Vertex = cppyy.gbl.flatsurf.Vertex

from sage.all import VectorSpace, FreeModule, matrix, identity_matrix, ZZ, QQ, Unknown, vector

from .subfield import subfield_from_elements
from .polygon import is_between, projectivization
from .translation_surface import TranslationSurface
from .pyflatsurf_conversion import to_pyflatsurf

class Decomposition:
    def __init__(self, gl2rorbit, decomposition, u):
        self.u = u
        self.orbit = gl2rorbit
        self.decomposition = decomposition

    def cylinders(self):
        return [comp for comp in self.components() if comp.cylinder() == True]

    def minimal_components(self):
        return [comp for comp in self.components() if comp.withoutPeriodicTrajectory() == True]

    def undetermined_components(self):
        return [comp for comp in self.components() if comp.cylinder() == False and comp.withoutPeriodicTrajectory() == False]

    def num_cylinders_minimals_undetermined(self):
        ncyl = 0
        nmin = 0
        nund = 0
        for comp in self.decomposition.components():
            if comp.cylinder() == True:
                assert comp.withoutPeriodicTrajectory() == False
                ncyl += 1
            elif comp.cylinder() == False:
                assert comp.withoutPeriodicTrajectory() == True
                nmin += 1
            else:
                nund += 1
        return (ncyl, nmin, nund)

    def __repr__(self):
        ncyl, nmin, nund = self.num_cylinders_minimals_undetermined()
        return "Flow decomposition with %d cylinders, %d minimal components and %d undetermined components" % (ncyl, nmin, nund)

    def is_completely_periodic(self):
        r"""
        Return whether this flow decomposition consists only of cylinders.
        """
        ncyl, nmin, nund = self.num_cylinders_minimals_undetermined()
        if nmin:
            return False
        elif nund:
            return Unknown
        else:
            return True

    def _spanning_tree_decomposition(self, sc_index, sc_comp):
        r"""
        Return

        - a list of indices of edges that form a basis
        - a matrix projection to the basis (modulo the face relations)
        """
        components = [c for c in self.decomposition.components()]

        n = len(sc_index)
        assert n % 2 == 0
        n //= 2

        for p in components[0].perimeter():
            break
        root = p.saddleConnection()
        t = {0: None} # face -> half edge to take to go to the root
        todo = [0]
        edges = []  # store edges in topological order to perform Gauss reduction
        while todo:
            i = todo.pop()
            c = components[i]
            for sc in c.perimeter():
                sc1 = -sc.saddleConnection()
                j = sc_comp[sc1]
                if j not in t:
                    t[j] = sc1
                    todo.append(j)
                    edges.append(sc1)

        # gauss reduction
        spanning_set = set(range(n))
        proj = identity_matrix(ZZ, n)
        edges.reverse()
        for sc1 in edges:
            i1 = sc_index[sc1]
            if i1 < 0:
                s1 = -1
                i1 = -i1-1
            else:
                s1 = 1
            comp = components[sc_comp[sc1]]
            proj[i1] = 0
            for p in comp.perimeter():
                sc = p.saddleConnection()
                if sc == sc1:
                    continue
                j = sc_index[sc]
                if j < 0:
                    s = -1
                    j = -j-1
                else:
                    s = 1
                proj[i1] = - s1 * s * proj[j]

            spanning_set.remove(i1)
            for j in range(n):
                assert proj[j,i1] == 0

        return (t, sorted(spanning_set), proj)

    def kontsevich_zorich_cocycle(self):
        r"""
        Base change for this flow decomposition.
        """
        components = [c for c in self.decomposition.components()]
        sc_pos = []
        sc_comp = {}
        sc_index = {}
        n = 0
        for i,comp in enumerate(components):
            for p in comp.perimeter():
                sc = p.saddleConnection()
                sc_comp[sc] = i
                if sc not in sc_index:
                    sc_index[sc] = n
                    sc_pos.append(sc)
                    sc_index[-sc] = -n-1
                    n += 1

        t, spanning_set, proj = self._spanning_tree_decomposition(sc_index, sc_comp)
        assert proj.rank() == len(spanning_set) == n - len(components) + 1, self.u
        proj = proj.transpose()
        proj = matrix(ZZ, [r for r in proj.rows() if not r.is_zero()])
        assert proj.nrows() == self.orbit.proj.nrows(), self.u

        # Write the base change V^*(T') -> V^*(T) relative to our bases
        A = matrix(ZZ, self.orbit.d)
        for i, sc in enumerate(spanning_set):
            sc = sc_pos[sc]
            c = sc.chain()
            v = [0] * self.orbit.d
            for edge in self.orbit._surface.edges():
                A[i] += ZZ(str(c[edge])) * self.orbit.proj.column(edge.index())
        assert A.det().is_unit()
        return A, sc_index, proj

    # TODO: move to C++
    # see https://github.com/flatsurf/flatsurf/pull/162
    def parabolic(self):
        r"""
        Return whether this decomposition is completely periodic with cylinder with
        commensurable moduli.

        EXAMPLES::

            sage: from flatsurf import translation_surfaces, GL2ROrbitClosure

        Veech surfaces have the property that any saddle connection direction is
        parabolic (one half of the Veech dichotomy)::

            sage: S = translation_surfaces.veech_double_n_gon(5)
            sage: O = GL2ROrbitClosure(S)
            sage: all(d.parabolic() for d in O.decompositions_depth_first(3))
            True

        For surfaces in rank one loci, even though they are completely periodic,
        they are generally not completely periodic::

            sage: S = translation_surfaces.mcmullen_genus2_prototype(4,2,1,1,1/4)
            sage: O = GL2ROrbitClosure(S)
            sage: all((d.decomposition.hasCylinder() == False) or d.parabolic() for d in O.decompositions(6, 100))
            False
            sage: all((d.decomposition.completelyPeriodic() == True) or (d.decomposition.hasCylinder() == False) for d in O.decompositions(6, 100))
            True

        .. TODO::

            Because of https://github.com/flatsurf/flatsurf/issues/140 we set a
            limit to decompositions but this should not be needed here.
        """
        if self.orbit.V2.sage_base_ring is ZZ or self.orbit.V2.sage_base_ring is QQ:
            return True

        # from here we assume that the field self.orbit.K is a number field
        # as we need to test whether some number of the form (a * b / (c * d))
        # are rationals
        state = True
        mod0 = None
        hol0 = None
        for comp in self.decomposition.components():
            if comp.cylinder() == False:
                return False
            elif comp.cylinder() != True:
                state = Unknown
            hol = comp.circumferenceHolonomy()
            hol = self.orbit.V2sage(self.orbit.V2(hol))
            area = self.orbit.Ksage_constructor(comp.area())
            mod = area / (hol[0]**2 + hol[1]**2)
            if mod0 is None:
                mod0 = mod
                hol0 = hol
            else:
                # check parallelism
                assert hol0[0] * hol[1] == hol0[1] * hol[0]
                if not (mod / mod0).is_rational():
                    return False
        return state

    def circumference_width(self, component, sc_index, proj):
        r"""
        Return the circumference and width of ``component`` in the coordinate of the original
        surface.
        """
        if component.cylinder() != True:
            raise ValueError

        A, sc_index, proj = self.kontsevich_zorich_cocycle()
        perimeters = [p for p in component.perimeter()]
        per = perimeters[0]
        assert not per.vertical()
        sc = per.saddleConnection()
        i = sc_index[sc]
        if i < 0:
            s = -1
            i = -i-1
        else:
            s = 1
        v = s * proj.column(i)
        circumference = -A.solve_right(v)

        # check
        hol = self.orbit.holonomy_dual(circumference)
        holbis = component.circumferenceHolonomy()
        holbis = self.orbit.V2sage(self.orbit.V2(holbis))
        assert hol == holbis, (hol, holbis)

        u = sc.vector()
        u = self.orbit.V2sage(self.orbit.V2(u))
        width = self.u[1] * u[0] - self.u[0] * u[1]
        widthbis = self.orbit.Ksage_constructor(component.width())
        assert width == widthbis, (width, widthbis)

        return circumference, width

    def cylinder_deformation_subspace(self):
        r"""
        Return a subspace included in the tangent space to the GL(2,R)-orbit closure.

        From A. Wright cylinder deformation Theorem.
        """
        v = self.orbit.V()
        modules = []
        vcyls = []
        A, sc_index, proj = self.kontsevich_zorich_cocycle()
        for comp in self.decomposition.components():
            if comp.cylinder() == False:
                continue
            elif comp.cylinder() == True:
                circ, width = self.circumference_width(comp, sc_index, proj)
                vcyls.append(width * circ)
                hol = comp.circumferenceHolonomy()
                hol = self.orbit.V2sage(self.orbit.V2(hol))
                area = self.orbit.Ksage_constructor(comp.area())
                modules.append(area / (hol[0]**2 + hol[1]**2))
            else:
                return []

        # irrationally related cylinders can be twisted independently
        vectors = []
        if self.orbit.V2.sage_base_ring is ZZ or self.orbit.V2.sage_base_ring is QQ:
            vectors.append(sum(vcyls))
        else:
            ncyls = len(vcyls)
            M = matrix([mod.vector() for mod in modules])
            relations = M.left_kernel().matrix()
            for t in relations.right_kernel().basis():
                vectors.append(sum(t[i] / modules[i] * vcyls[i] for i in range(ncyls)))

        return vectors

    def plot_completely_periodic(self):
        from sage.plot.all import polygon2d, Graphics, point2d, text
        O = self.orbit
        G = []
        u = self.u  # direction (that we put horizontal)
        m = matrix(2, [u[1], -u[0], u[1], u[0]])
        indices = {}
        xmin = xmax = ymin = ymax = 0
        for comp in self.decomposition.components():
            H = Graphics()
            x = O.V2sage.zero()

            pts = [x]
            below = True
            for p in comp.perimeter():
                sc = p.saddleConnection()
                y = x + m * O.V2sage(O.V2(p.saddleConnection().vector()))

                if p.vertical():
                    if sc in indices:
                        i = indices[sc]
                    else:
                        i = len(indices) // 2
                        indices[sc] = i
                        indices[-sc] = i
                    if below:
                        H += text(str(i), (x+y)/2, color='black')
                x = y
                xmin = min(xmin, x[0])
                xmax = max(xmax, x[0])
                ymin = min(ymin, x[1])
                ymax = max(ymax, x[1])
                pts.append(x)
            H += polygon2d(pts, color='blue', alpha=0.3)
            H += point2d(pts, color='red', pointsize=20)
            G.append(H)
        aspect_ratio = float(xmax - xmin) / float(ymax - ymin)
        for H in G:
            H.set_axes_range(xmin, xmax, ymin, ymax)
            H.axes(False)
            H.set_aspect_ratio(aspect_ratio)
        return G

class GL2ROrbitClosure:
    r"""
    Lower bound approximation to the tangent space of a GL(2,R)-orbit closure of a
    linear family of translation surfaces.

    EXAMPLES::

        sage: from flatsurf import polygons, similarity_surfaces, GL2ROrbitClosure
        sage: T = polygons.triangle(3, 3, 5)
        sage: S = similarity_surfaces.billiard(T)
        sage: S = S.minimal_cover(cover_type="translation")
        sage: O = GL2ROrbitClosure(S)
        sage: O
        GL(2,R)-orbit closure of dimension at least 2 in H_5(4, 2^2) (ambient dimension 12)
    """
    def __init__(self, surface):
        if not isinstance(surface, TranslationSurface):
            raise ValueError("input must be a translation surface")
        self._surface = to_pyflatsurf(surface)   # underlying libflatsurf surface

        # We construct a spanning set of edges, that is a subset of the
        # edges that form a basis of H_1(S, Sigma; Z)
        # It comes together with a projection matrix
        surface = self._surface
        t, m = self._spanning_tree()
        assert set(t.keys()) == set(f[0] for f in self._faces())
        self.spanning_set = []
        v = set(t.values())
        for e in self._surface.edges():
            if e.positive() not in v and e.negative() not in v:
                self.spanning_set.append(e)
        self.d = len(self.spanning_set)
        assert 3*self.d - 3 == self._surface.size()
        assert m.rank() == self.d
        m = m.transpose()
        # projection matrix from Z^E to H_1(S, Sigma; Z) in the basis
        # of spanning edges
        self.proj = matrix(ZZ, [r for r in m.rows() if not r.is_zero()])

        self.Omega = self._intersection_matrix(t, self.spanning_set)

        # TODO: this distinction between mpz/mpq/renf_elem_class is somehow annoying
        # (and we completely ignore exact real)
        x = surface.fromEdge(surface.halfEdges()[0]).x()
        if isinstance(x, cppyy.gbl.eantic.renf_elem_class):
            base = x.parent()
        else:
            base = type(x)
        self.V2 = pyflatsurf.vector.Vectors(base)
        self.V2sage = VectorSpace(self.V2.sage_base_ring, 2)

        if self.V2.sage_base_ring is ZZ or self.V2.sage_base_ring is QQ:
            self.Ksage_constructor = lambda x: self.V2.sage_base_ring(str(x))
        else:
            self.Ksage_constructor = lambda x: self.V2.sage_base_ring(self.V2.base_ring()(x))

        self.V = VectorSpace(self.V2.sage_base_ring, self.d)
        self.H = matrix(self.V2.sage_base_ring, self.d, 2)
        for i in range(self.d):
            s = self._surface.fromEdge(self.spanning_set[i].positive())
            self.H[i] = self.V2sage(self.V2(s))
        self.Hdual = self.Omega * self.H

        # NOTE: we don't use Sage vector spaces because they are usually way too slow
        # (we avoid calling .echelonize())
        self._U = matrix(self.V2.sage_base_ring, self.d)
        self._U[:2] = self.H.transpose()
        self._U_rank = 2

    def dimension(self):
        return self._U_rank

    def ambient_stratum(self):
        from surface_dynamics import AbelianStratum
        surface = self._surface
        angles = [surface.angle(v) for v in surface.vertices()]
        return AbelianStratum([a-1 for a in angles])

    def base_ring(self):
        return self._U.base_ring()

    def field_of_definition(self):
        r"""
        Return the field of definition of the current subspace.

        .. WARNING::

            This involves the computation of the echelon form of the matrix. It
            might be rather expensive if the computation of the tangent space is
            not terminated.
        """
        M = self._U.echelon_form()
        L, elts, phi = subfield_from_elements(self.base_ring(), M[:self._U_rank].list())
        return L

    def _half_edge_to_face(self, h):
        surface = self._surface
        h1 = h
        h2 = surface.nextInFace(h1)
        h3 = surface.nextInFace(h2)
        return min([h1, h2, h3], key=lambda x: x.index())

    def _faces(self):
        seen = set()
        faces = []
        surface = self._surface
        for e in surface.edges():
            for h1 in [e.positive(), e.negative()]:
                if h1 in seen:
                    continue
                h2 = surface.nextInFace(h1)
                h3 = surface.nextInFace(h2)
                faces.append((h1, h2, h3))
                seen.add(h1)
                seen.add(h2)
                seen.add(h3)
        return faces

    def __repr__(self):
        return "GL(2,R)-orbit closure of dimension at least %d in %s (ambient dimension %d)" % (self._U_rank, self.ambient_stratum(), self.d)

    def holonomy(self, v):
        r"""
        Return the holonomy of ``v`` (with respect to the basis)
        """
        return self.V(v) * self.H

    def holonomy_dual(self, v):
        return self.V(v) * self.Hdual

    def tangent_space_basis(self):
        return self._U[:self._U_rank].rows()

    def lift(self, v):
        r"""
        Given a vector in the "spanning set basis" return a vector on the full basis of
        edges.

        EXAMPLES::

            sage: from flatsurf import (polygons, translation_surfaces,
            ....:       similarity_surfaces, GL2ROrbitClosure)

            sage: S = translation_surfaces.mcmullen_genus2_prototype(4,2,1,1,0)
            sage: O = GL2ROrbitClosure(S)
            sage: u0,u1 = O.tangent_space_basis()
            sage: v0 = O.lift(u0)
            sage: v1 = O.lift(u1)
            sage: span([v0, v1])
            Vector space of degree 9 and dimension 2 over Number Field in l with defining polynomial x^2 - x - 8 with l = 3.372281323269015?
            Basis matrix:
            [           1            0           -1  1/4*l - 1/4 -1/4*l + 1/4            0 -1/4*l + 1/4            0 -1/4*l + 1/4]
            [           0            1           -1  1/8*l + 7/8 -1/8*l + 1/8           -1 3/8*l - 11/8 -1/2*l + 3/2 -1/8*l + 1/8]

        This can be used to deform the surface::

            sage: T = polygons.triangle(3,4,13)
            sage: S = similarity_surfaces.billiard(T)
            sage: S = S.minimal_cover("translation").erase_marked_points()
            sage: O = GL2ROrbitClosure(S)
            sage: for d in O.decompositions(4, 20):
            ....:     O.update_tangent_space_from_flow_decomposition(d)
            ....:     if O.dimension() == 4:
            ....:         break
            sage: d1,d2,d3,d4 = [O.lift(b) for b in O.tangent_space_basis()]
            sage: dreal = d1/132 + d2/227 + d3/280 - d4/201
            sage: dimag = d1/141 - d2/233 + d4/230 + d4/250
            sage: d = [O.V2((x,y)).vector for x,y in zip(dreal,dimag)]

        TODO: This is waiting for https://github.com/flatsurf/flatsurf/issues/145::

            sage: S2 = O._surface + d  # not tested
            sage: O2 = GL2ROrbitClosure(S2)   # not tested
            sage: for d in O2.decompositions(4, 20, sector=((1,0),(5,1))):  # not tested
            ....:     O2.update_tangent_space_from_flow_decomposition(d)
        """
        # given the values on the spanning edges we reconstruct the unique vector that
        # vanishes on the boundary
        bdry = self.boundaries()
        n = self._surface.edges().size()
        k = len(self.spanning_set)
        assert k + len(bdry) == n + 1
        A = matrix(self.V2.sage_base_ring, n+1, n)
        for i,e in enumerate(self.spanning_set):
            A[i,e.index()] = 1
        for i,b in enumerate(bdry):
            A[k+i,:] = b
        u = vector(self.V2.sage_base_ring, n + 1)
        u[:k] = v
        return A.solve_right(u)

    def absolute_homology(self):
        vert_index = {v:i for i,v in enumerate(self._surface.vertices())}
        m = len(vert_index)
        if m == 1:
            return self.V
        rows = []
        for e in self.spanning_set:
            r = [0] * m
            i = vert_index[Vertex.target(e.positive(), self._surface)]
            j = vert_index[Vertex.source(e.positive(), self._surface)]
            if i != j:
                r[i] = 1
                r[j] = -1
            rows.append(r)
        return matrix(rows).left_kernel()

    def absolute_dimension(self):
        r"""
        EXAMPLES::

            sage: from flatsurf import polygons, similarity_surfaces, GL2ROrbitClosure
            sage: T = polygons.triangle(1,3,4)  # Veech octagon
            sage: S = similarity_surfaces.billiard(T)
            sage: S = S.minimal_cover("translation")
            sage: O = GL2ROrbitClosure(S)
            sage: O.absolute_dimension()
            2

        The triangular billiard (5,6,7) belongs to the canonical double cover of
        the stratum Q(5,3,0^3) in genus 3. The orbit is dense and we can check
        that the absolute dimension is indeed `6 = 2 rank`::

            sage: T = polygons.triangle(5,6,7)
            sage: S = similarity_surfaces.billiard(T)
            sage: S = S.minimal_cover("translation")
            sage: O = GL2ROrbitClosure(S)
            sage: for d in O.decompositions(5, 100):
            ....:     O.update_tangent_space_from_flow_decomposition(d)
            ....:     if O.dimension() == 9:
            ....:         break
            sage: O.absolute_dimension()
            6
        """
        return (self.absolute_homology().matrix() * self._U[:self._U_rank].transpose()).rank()

    def _spanning_tree(self, root=None):
        r"""
        Return

        - a list of indices of edges that form a basis
        - a matrix projection to the basis (modulo the triangle relations)
        """
        if root is None:
            root = next(iter(self._surface.edges())).positive()

        root = self._half_edge_to_face(root)
        t = {root: None} # face -> half edge to take to go to the root
        todo = [root]
        edges = []  # store edges in topological order to perform Gauss reduction
        while todo:
            f = todo.pop()
            for _ in range(3):
                f1 = -f
                g = self._half_edge_to_face(f1)
                if g not in t:
                    t[g] = f1
                    todo.append(g)
                    edges.append(f1)

                f = self._surface.nextInFace(f)

        # gauss reduction
        n = self._surface.size()
        proj = identity_matrix(ZZ, n)
        edges.reverse()
        for f1 in edges:
            v = [0] * n
            f2 = self._surface.nextInFace(f1)
            f3 = self._surface.nextInFace(f2)
            assert self._surface.nextInFace(f3) == f1

            i1 = f1.index()
            s1 = -1 if i1%2 else 1
            i2 = f2.index()
            s2 = -1 if i2%2 else 1
            i3 = f3.index()
            s3 = -1 if i3%2 else 1
            i1 = f1.edge().index()
            i2 = f2.edge().index()
            i3 = f3.edge().index()
            proj[i1] = -s1*(s2*proj[i2] + s3*proj[i3])
            for j in range(n):
                assert proj[j,i1] == 0

        return (t, proj)

    def _intersection_matrix(self, t, spanning_set):
        r"""
        Given a spanning tree, compute the associated intersection matrix.

        It can be used to compute holonomies. (we can be off by a - sign)
        """
        d = len(spanning_set)
        h = spanning_set[0].positive()
        all_edges = set([e.positive() for e in spanning_set])
        all_edges.update([e.negative() for e in spanning_set])
        contour = []
        contour_inv = {}   # half edge -> position in contour
        while h not in contour_inv:
            contour_inv[h] = len(contour)
            contour.append(h)
            h = self._surface.nextAtVertex(-h)
            while h not in all_edges:
                h = self._surface.nextAtVertex(h)

        assert len(contour) == len(all_edges)

        # two curves intersect when their relative position in the contour
        # are x y x y or y x y x
        Omega = matrix(ZZ, d)
        for i in range(len(spanning_set)):
            ei = spanning_set[i]
            pi1 = contour_inv[ei.positive()]
            pi2 = contour_inv[ei.negative()]
            if pi1 > pi2:
                si = -1
                pi1, pi2 = pi2, pi1
            else:
                si = 1
            for j in range(i+1, len(spanning_set)):
                ej = spanning_set[j]
                pj1 = contour_inv[ej.positive()]
                pj2 = contour_inv[ej.negative()]
                if pj1 > pj2:
                    sj = -1
                    pj1, pj2 = pj2, pj1
                else:
                    sj = 1

                # pj1 pj2 pi1 pi2: pj2 < pi1
                # pi1 pi2 pj1 pj2: pi2 < pj1
                # pi1 pj1 pj2 pi2: pi1 < pj1 and pj2 < pi2
                # pj1 pi1 pi2 pj2: pj1 < pi1 and pi2 < pj2
                if (pj2 < pi1) or (pi2 < pj1) or \
                   (pj1 > pi1 and pj2 < pi2) or \
                   (pj1 < pi1 and pj2 > pi2):
                    # no intersection
                    continue

                if pi1 < pj1 < pi2:
                    # one sign
                    Omega[i,j] = si * sj
                else:
                    # other sign
                    assert pi1 < pj2 < pi2, (pi1, pi2, pj1, pj2)
                    Omega[i,j] = -si*sj
                Omega[j,i] = - Omega[i,j]
        return Omega

    def boundaries(self):
        r"""
        Return the list of boundaries (ie sum of edges around a triangular face).

        These are elements of H_1(S, Sigma; Z).

        TESTS::

            sage: from flatsurf import polygons, similarity_surfaces, GL2ROrbitClosure

            sage: from itertools import product
            sage: for a in range(1,5):
            ....:     for b in range(a, 5):
            ....:         for c in range(b, 5):
            ....:             if gcd([a, b, c]) != 1 or (a,b,c) == (1,1,2):
            ....:                 continue
            ....:             T = polygons.triangle(a, b, c)
            ....:             S = similarity_surfaces.billiard(T)
            ....:             S = S.minimal_cover(cover_type="translation")
            ....:             O = GL2ROrbitClosure(S)
            ....:             for b in O.boundaries():
            ....:                 assert (O.proj * b).is_zero()
        """
        n = self._surface.size()
        V = FreeModule(ZZ, n)
        B = []
        for (f1,f2,f3) in self._faces():
            i1 = f1.index()
            s1 = -1 if i1%2 else 1
            i2 = f2.index()
            s2 = -1 if i2%2 else 1
            i3 = f3.index()
            s3 = -1 if i3%2 else 1
            i1 = f1.edge().index()
            i2 = f2.edge().index()
            i3 = f3.edge().index()
            v = [0] * n
            v[i1] = 1
            v[i2] = s1 * s2
            v[i3] = s1 * s3
            B.append(V(v))
            B[-1].set_immutable()

        return B

    def decomposition(self, v, limit=-1):
        v = self.V2(v)
        decomposition = pyflatsurf.flatsurf.makeFlowDecomposition(self._surface, v.vector)
        u = self.V2sage(v)
        if limit != 0:
            pyflatsurf.flatsurf.decomposeFlowDecomposition(decomposition, int(limit))
        return Decomposition(self, decomposition, u)

    def decompositions_depth_first(self, bound, limit=-1, sector=None, visited=None):
        # TODO: make the sector restriction at C++ level *without* filtering
        limit = int(limit)
        if visited is None:
            visited = set()
        for connection in self._surface.saddle_connections(pyflatsurf.flatsurf.Bound(int(bound), 0)):
            v = connection.vector()
            slope = self.V2sage(self.V2(v))
            if slope[1].is_zero():
                slope = self.V2sage((1, 0))
            else:
                slope = slope / slope[1]
            if sector is not None and not is_between(sector[0], sector[1], slope):
                continue
            slope.set_immutable()
            if slope in visited:
                continue
            visited.add(slope)
            yield self.decomposition(v, limit)

    def decompositions_breadth_first(self, bound, limit=-1, sector=None, visited=None):
        # TODO: make the sector restriction at C++ level *without* filtering
        limit = int(limit)
        if visited is None:
            visited = set()
        for i in range(bound + 1):
            for connection in self._surface.saddle_connections(flatsurf.Bound(i, 0)):
                v = connection.vector()
                slope = self.V2sage(self.V2(v))
                if slope[1].is_zero():
                    slope = self.V2sage((1, 0))
                else:
                    slope = slope / slope[1]
                if sector is not None and not is_between(sector[0], sector[1], slope):
                    continue
                slope.set_immutable()
                if slope in visited:
                    continue
                visited.add(slope)
                yield self.decomposition(v, limit)

    decompositions = decompositions_depth_first

    def is_teichmueller_curve(self, bound, limit=-1):
        r"""
        Return ``False`` when the program can find a direction which is either completely
        periodic with incomensurable moduli or a direction with at least one cylinder
        and at least one minimal component.

        EXAMPLES::

            sage: from flatsurf import polygons, similarity_surfaces, GL2ROrbitClosure
            sage: for a in range(1,6):
            ....:     for b in range(a,6):
            ....:         for c in range(b,6):
            ....:             if a + b + c > 7 or gcd([a,b,c]) != 1:
            ....:                 continue
            ....:             T = polygons.triangle(a, b, c)
            ....:             S = similarity_surfaces.billiard(T)
            ....:             S = S.minimal_cover(cover_type="translation")
            ....:             O = GL2ROrbitClosure(S)
            ....:             if O.is_teichmueller_curve(3, 50) != False:
            ....:                 print(a,b,c)
            1 1 1
            1 1 2
            1 1 4
            1 2 2
            1 2 3
            1 3 3
        """
        if self.V2.sage_base_ring is ZZ or self.V2.sage_base_ring is QQ:
            # square tiled surface
            return True
        # TODO: implement simpler criterion based on the holonomy field
        # (e.g. one can compute the trace field and verify that it is
        #  totally real, of degree at most the genus and that the surface
        #  is algebraically completely periodic)
        for decomposition in self.decompositions_depth_first(bound, limit):
            if decomposition.parabolic() == False:
                return False
        # TODO: from there on one should run the program of Ronen Mukamel (or
        # something similar) to certify that we do have a Veech surface
        return Unknown

    def update_tangent_space_from_flow_decomposition(self, decomposition, verbose=False):
        r"""
        Update the current tangent space by using the cylinder deformation vector from ``decomposition``.

        EXAMPLES::

            sage: from flatsurf import polygons, similarity_surfaces, GL2ROrbitClosure

            sage: T = polygons.triangle(1, 2, 5)
            sage: S = similarity_surfaces.billiard(T)
            sage: S = S.minimal_cover(cover_type="translation")
            sage: O = GL2ROrbitClosure(S)
            sage: for d in O.decompositions(3, 50):
            ....:     O.update_tangent_space_from_flow_decomposition(d)
            sage: assert O.dimension() == 2
        """
        A = self._U
        i = self._U_rank
        if self._U_rank == self._U.nrows():
            return
        for v in decomposition.cylinder_deformation_subspace():
            A[i] = v
            r = A.rank()
            if r > i:
                assert r == i+1
                i = self._U_rank = i + 1
                if self._U_rank == self._U.nrows():
                    return

