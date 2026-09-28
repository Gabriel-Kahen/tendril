# Local feedback and regulatory dynamics

Implemented September 23, 2026. This is the explicit model Tendril executes, not a claim of biological realism. The implementation is in `signals.py`, `simulation.py` and `World.contact_segments()`.

## Separate the three clocks

Physics advances every integration step. Regulatory signals advance by the same elapsed physical time, in juveniles and adults. Muscle commands sample signal, joint strain and contact at the control interval. Development may edit topology at its slower growth interval, only during juvenile development.

For each step, due developmental edits occur first, then due control updates, then the accepted mechanical step, then signal propagation over that step. Thus a new site participates from its birth, and a controller never reads a signal from future physical time. Signals do not receive a growth-interval-sized jump at time zero. Ending development stops edits, not regulation.

The controller remains local: a module's oscillator, joint-strain gain, binary contact gain and regulatory-signal gain produce bounded muscle activation. Existing force, speed, shortening, power and work-budget limits remain in force.

## The signal model

Each structural site has a signed, dimensionless regulatory state `s_i` bounded to `[-5, 5]`. It inherits the emission parameter and control gains of its module. New sites start with zero state; their parent's instantaneous state is not copied or depleted.

Between topology changes, the intended unsaturated dynamics are:

\[
\frac{d s_i}{dt}=e_i-\lambda s_i+D\sum_{j\in N(i)}(s_j-s_i).
\]

Here `e_i` is the inherited constant `signal_emit`; `D` is `signal_diffusion`; and `lambda` is `signal_decay`. The graph is the undirected union of tree joints and accepted loop connections. Duplicate edges do not increase conductance. Tissue belongs to its supporting site; it does not add separate signal nodes.

Let `L` be the graph Laplacian and `A = D L + lambda I`. Over a physical step of length `h`, the linear solution is:

\[
s(t+h)=\exp(-Ah)s(t)+\phi_h(A)e,
\quad
\phi_h(r)=\begin{cases}(1-\exp(-rh))/r&r>0,\\h&r=0.\end{cases}
\]

The implementation diagonalizes the symmetric Laplacian and caches the two propagation matrices by graph, duration and rates. It uses `expm1` for the source term and zeros roundoff-sized eigenvalues before scaling by diffusion. This preserves uniform modes even at large diffusion rates. For the current small bodies, this avoids explicit-Euler stability restrictions without requiring many signal substeps.

Dense matrices cost quadratic storage and each new eigensystem costs cubic work in site count. This fits the current default limit of 32 sites; substantially larger bodies should revisit that solver choice.

After every step, values are clipped to the model's fixed state bounds. The linear propagation is exact up to floating-point error; the entire saturated, developing, mechanically coupled system is not timestep-independent. Crossing saturation and changing topology are discrete events and must still be checked under timestep refinement.

## What the abstraction means

- Diffusion without source, decay or saturation conserves the sum of site states within each connected component. That is a numerical invariant, not conservation of chemical mass or mechanical energy.
- Equal conductance per connection makes highly connected sites exchange state faster. Physical edge length, tissue volume, transport delay and channel cross-section are not represented.
- Emission is currently constant per inherited module. Contact and strain affect local control and growth directly; they do not yet modulate emitted signals. Continuous regulation is therefore not a sensory communication network.
- Negative state is regulatory inhibition, not negative material. Emission, decay and saturation can change the sum of states. Growth changes the graph and adds zero-state sites, preserving the sum at insertion but changing the mean.
- Regulation currently has no separate metabolic/computational energy cost. Mechanical actuation and material insertion retain their existing accounting.

## Contact ownership

Only solver-participating MuJoCo contacts count: `exclude == 0` and `efc_address >= 0`. This is an active constraint predicate, not a measurement of nonzero normal force. Force-generating contact margins count; mere proximity, excluded pairs and contacts without active constraint rows do not.

A capsule contact reports to its own site. A tissue contact reports to its supporting site. A flexible-link contact reports to both connected sites. Each site receives one boolean contact state regardless of how many contact points a mesh produces, so finer tessellation does not multiply the controller's contact gain.

This ownership convention is deliberately coarse. It does not report contact direction, force magnitude or the precise position within a tissue patch or link. Those would require explicit sensor definitions and inherited response parameters.

## Verification

Analytic tests cover isolated source/decay, two-site diffusion, disconnected components, constant modes at high diffusion rates, elapsed-time partitioning and saturation. Topology tests cover newborn state and loop conductance. Actual MuJoCo tests cover tissue-floor contact driving muscles, link-floor attribution, capsule contact margins and excluded touching pairs. Adult assays record initial/final signals and clone biological state independently.

These checks establish the implemented semantics. They do not show that the signals are useful to evolution or that the chosen contact sensing model is optimal.

## Next theoretical decision: qualification without a task mandate

Automatic archive qualification should keep three types of evidence separate:

1. **Physical validity:** every checked rollout respects strain, collision, speed and resource limits.
2. **Numerical sensitivity:** finer timesteps preserve validity; report topology changes and capability differences with unit-specific absolute and relative tolerances.
3. **Behavioral variability:** repeated, recorded perturbations provide outcome distributions. A few trials describe sampled behavior, not a universal robustness guarantee.

A passive but valid developmental precursor must be able to qualify without locomotion or manipulation. Structural admission and claims about mature capability should have separate evidence/status fields. Descriptor-bin changes alone should not be treated as physical failure. Rejected trials must remain inspectable.

This qualification scheme is a proposal for the next implementation milestone; archive admission still uses the primary evaluation today. A later sensory-signaling extension could add bounded contact/strain-dependent emission, but should be explicit in the genome and tested rather than inferred from the current scalar state.
