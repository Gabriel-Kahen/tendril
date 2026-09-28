"""MuJoCo mechanics; development edits model topology, never advances physics itself."""

from __future__ import annotations

import math
import time
import xml.etree.ElementTree as ET
from copy import deepcopy
from dataclasses import asdict, dataclass

import mujoco as mj
import numpy as np
from scipy.spatial.transform import Rotation

from .config import SimulationConfig
from .elasticity import (
    flex_deformation_metrics,
    flex_elastic_energy,
    flex_reference_positions,
)


def numbers(values):
    return " ".join(f"{float(v):.12g}" for v in values)


def add(parent, tag, **attrs):
    return ET.SubElement(parent, tag, {k: str(v) for k, v in attrs.items()})


def direction_quat(direction):
    v = np.asarray(direction, dtype=float)
    v /= np.linalg.norm(v)
    if v[2] < -0.999999:
        return [0.0, 1.0, 0.0, 0.0]
    q = np.array([1 + v[2], -v[1], v[0], 0.0])
    return (q / np.linalg.norm(q)).tolist()


@dataclass
class Segment:
    id: int
    parent: int | None
    module: str
    length: float
    radius: float
    stiffness: float
    damping: float
    quat: list
    born: float
    depth: int = 0
    grown: bool = False
    signal: float = 0.0


@dataclass
class Link:
    id: int
    a: int
    b: int
    rest: float
    stiffness: float = 5.0


def segment_distance(p1, q1, p2, q2):
    # Closest points on finite segments, including parallel/degenerate cases.
    u, v, w = q1 - p1, q2 - p2, p1 - p2
    a, b, c, d, e = u @ u, u @ v, v @ v, u @ w, v @ w
    if a < 1e-15 or c < 1e-15:
        return float(np.linalg.norm(w))
    denom = a * c - b * b
    s = np.clip((b * e - c * d) / denom, 0, 1) if denom > 1e-15 else 0.0
    t = (b * s + e) / c
    if t < 0:
        t, s = 0.0, np.clip(-d / a, 0, 1)
    elif t > 1:
        t, s = 1.0, np.clip((b - d) / a, 0, 1)
    return float(np.linalg.norm(w + s * u - t * v))


class World:
    def __init__(self, genome: dict, config: SimulationConfig):
        self.config = config
        self.modules = {m["id"]: deepcopy(m) for m in genome["modules"]}
        m = self.modules[genome["root"]]
        self.segments = [
            Segment(
                0,
                None,
                m["id"],
                m["length"],
                m["radius"],
                m["stiffness"],
                m["damping"],
                [1.0, 0.0, 0.0, 0.0],
                0.0,
            )
        ]
        self.links: list[Link] = []
        self.tissues: list[int] = []
        self.events: list[dict] = []
        self.spent = 0.0
        self.work = 0.0
        self.external_work = 0.0
        self.growth_energy = 0.0
        self.edit_seconds = 0.0
        self.max_contact_penetration = 0.0
        self.tissue_min_volume = 1.0
        self.tissue_max_strain = 0.0
        self.floor_contacts = 0
        self.self_contacts = 0
        self.model, self.data = self.compile()
        self.initial_energy = self.energy()
        self.initial_mass = self.mass()
        self.spent = self.initial_mass * config.growth_cost_per_kg + max(
            0.0, self.initial_energy
        )
        self.flex_reference = flex_reference_positions(self.model)
        self.muscle_reference = {}
        self.positive_work = 0.0
        self.previous_control = np.zeros(self.model.nu)
        self.events.append(
            {
                "type": "seed",
                "time": 0.0,
                "mass": self.initial_mass,
                "energy": self.initial_energy,
                "charge": self.spent,
            }
        )

    def xml(self):
        c = self.config
        root = ET.Element("mujoco", model="tendril")
        add(root, "compiler", angle="radian", autolimits="true")
        option = add(
            root,
            "option",
            timestep=c.timestep,
            gravity="0 0 -9.81",
            integrator="discrete" if self.tissues else "implicitfast",
            iterations=80,
            tolerance="1e-10",
        )
        add(option, "flag", energy="enable")
        default = add(root, "default")
        add(
            default,
            "geom",
            friction="0.8 0.01 0.001",
            solref="0.008 1",
            solimp="0.95 0.99 0.001",
        )
        world = add(root, "worldbody")
        add(world, "light", pos="0 -2 3", dir="0 1 -1")
        add(
            world,
            "geom",
            name="floor",
            type="plane",
            size="5 5 .1",
            rgba=".15 .19 .21 1",
        )
        obj = add(world, "body", name="object", pos=".27 .08 .025")
        add(obj, "freejoint", name="object_free")
        add(
            obj,
            "geom",
            name="object_geom",
            type="sphere",
            size=".025",
            mass=".025",
            rgba=".95 .55 .15 1",
        )
        bodies = {}
        tendons = add(root, "tendon")
        actuators = add(root, "actuator")
        contact = add(root, "contact")
        deformable = add(root, "deformable")
        for s in self.segments:
            container = world if s.parent is None else bodies[s.parent]
            pos = (
                [0, 0, c.seed_height]
                if s.parent is None
                else [0, 0, self.segments[s.parent].length]
            )
            body = add(
                container,
                "body",
                name=f"s{s.id}",
                pos=numbers(pos),
                quat=numbers(s.quat),
            )
            bodies[s.id] = body
            if s.parent is None:
                add(body, "freejoint", name="root")
            else:
                add(
                    body,
                    "joint",
                    name=f"j{s.id}",
                    type="ball",
                    stiffness=s.stiffness,
                    damping=s.damping,
                    limited="true",
                    range="0 1.3",
                )
                add(contact, "exclude", body1=f"s{s.parent}", body2=f"s{s.id}")
            add(
                body,
                "geom",
                name=f"g{s.id}",
                type="capsule",
                fromto=f"0 0 {0 if s.parent is None else min(s.radius * 2, s.length * 0.4)} 0 0 {s.length}",
                size=s.radius,
                density=c.density,
                rgba=".3 .72 .55 1",
            )
            for link in self.links:
                if s.id in (link.a, link.b):
                    add(
                        body,
                        "geom",
                        type="sphere",
                        size=".003",
                        pos=f"0 0 {s.length}",
                        mass=math.pi * 0.003**2 * link.rest * c.density / 2,
                        contype="0",
                        conaffinity="0",
                        rgba="0 0 0 0",
                    )
            add(body, "site", name=f"tip{s.id}", pos=f"0 0 {s.length}", size=".003")
            for k in range(3):
                phi = k * 2 * math.pi / 3
                x, y = s.radius * 1.15 * np.cos(phi), s.radius * 1.15 * np.sin(phi)
                add(
                    body,
                    "site",
                    name=f"prox{s.id}_{k}",
                    pos=numbers([x, y, min(s.length * 0.4, s.radius * 3)]),
                    size=".001",
                )
                add(
                    body,
                    "site",
                    name=f"dist{s.id}_{k}",
                    pos=numbers([x, y, s.length - min(s.length * 0.4, s.radius * 3)]),
                    size=".001",
                )
                if s.parent is not None:
                    name = f"muscle{s.id}_{k}"
                    tendon = add(
                        tendons, "spatial", name=name, width=".001", rgba=".75 .3 .35 1"
                    )
                    add(tendon, "site", site=f"dist{s.parent}_{k}")
                    add(tendon, "site", site=f"prox{s.id}_{k}")
                    add(
                        actuators,
                        "motor",
                        name=name,
                        tendon=name,
                        gear="1",
                        ctrllimited="true",
                        ctrlrange=f"-{c.muscle_force} 0",
                        forcelimited="true",
                        forcerange=f"-{c.muscle_force} 0",
                    )
            if s.id in self.tissues:
                flex = add(
                    body,
                    "flexcomp",
                    name=f"tissue{s.id}",
                    type="grid",
                    dim=3,
                    count="3 3 3",
                    spacing=numbers([c.tissue_spacing] * 3),
                    pos=f"{s.radius + c.tissue_spacing + 0.002} 0 {s.length * 0.5}",
                    radius=".002",
                    mass=c.tissue_mass,
                )
                add(
                    flex,
                    "elasticity",
                    young=c.tissue_young,
                    poisson=c.tissue_poisson,
                    damping=".005",
                )
                add(flex, "contact", selfcollide="auto", internal="false")
                add(flex, "pin", id="0 1 2 3 4 5 6 7 8")
                add(
                    body,
                    "geom",
                    type="sphere",
                    size=".001",
                    pos=f"{s.radius + 0.002} 0 {s.length * 0.5}",
                    mass=c.tissue_mass / 3,
                    contype="0",
                    conaffinity="0",
                    rgba="0 0 0 0",
                )
        for link in self.links:
            flex = add(
                deformable,
                "flex",
                name=f"link{link.id}",
                dim=1,
                body=f"s{link.a} s{link.b}",
                vertex=f"0 0 {self.segments[link.a].length} 0 0 {self.segments[link.b].length}",
                element="0 1",
                radius=".003",
                rgba=".65 .65 .9 1",
            )
            add(flex, "edge", stiffness=link.stiffness, damping=".08")
            add(flex, "contact", selfcollide="auto", internal="false")
        return ET.tostring(root, encoding="unicode")

    def compile(self):
        spec = mj.MjSpec.from_string(self.xml())
        counts = {}
        for joint in spec.joints:
            if not joint.name:
                body = joint.parent.name
                counts[body] = counts.get(body, 0) + 1
                joint.name = f"{body}_dof{counts[body]}"
        model = spec.compile()
        data = mj.MjData(model)
        for link in self.links:
            fid = mj.mj_name2id(model, mj.mjtObj.mjOBJ_FLEX, f"link{link.id}")
            model.flexedge_length0[model.flex_edgeadr[fid]] = link.rest
        mj.mj_forward(model, data)
        return model, data

    def energy(self):
        mj.mj_energyPos(self.model, self.data)
        mj.mj_energyVel(self.model, self.data)
        return float(sum(self.data.energy)) + flex_elastic_energy(self.model, self.data)

    def mass(self):
        return float(sum(self.model.body_mass) - self.model.body("object").mass[0])

    def momentum(self):
        result = np.zeros(3)
        for i in range(1, self.model.nbody):
            if self.model.body(i).name == "object":
                continue
            vel = np.zeros(6)
            mj.mj_objectVelocity(self.model, self.data, mj.mjtObj.mjOBJ_BODY, i, vel, 0)
            result += self.model.body_mass[i] * vel[3:]
        return result

    def positions(self):
        return np.array(
            [self.data.site(f"tip{s.id}").xpos for s in self.segments]
        )

    def endpoints(self, s):
        return self.data.body(f"s{s.id}").xpos.copy(), self.data.site(
            f"tip{s.id}"
        ).xpos.copy()

    def transfer(self, model, data):
        widths = {0: (7, 6), 1: (4, 3), 2: (1, 1), 3: (1, 1)}
        for j in range(self.model.njnt):
            name = self.model.joint(j).name
            new = mj.mj_name2id(model, mj.mjtObj.mjOBJ_JOINT, name)
            if new < 0:
                raise ValueError(f"Edit removed live joint {name}")
            nq, nv = widths[self.model.jnt_type[j]]
            a, b = self.model.jnt_qposadr[j], model.jnt_qposadr[new]
            data.qpos[b : b + nq] = self.data.qpos[a : a + nq]
            a, b = self.model.jnt_dofadr[j], model.jnt_dofadr[new]
            data.qvel[b : b + nv] = self.data.qvel[a : a + nv]
            data.qacc_warmstart[b : b + nv] = self.data.qacc_warmstart[a : a + nv]
        for a in range(self.model.nu):
            new = mj.mj_name2id(
                model, mj.mjtObj.mjOBJ_ACTUATOR, self.model.actuator(a).name
            )
            if new >= 0:
                data.ctrl[new] = self.data.ctrl[a]
        data.time = self.data.time
        mj.mj_forward(model, data)

    def edit(self, kind, mutate, detail):
        before = self.energy()
        mass = self.mass()
        momentum = self.momentum()
        poses = {
            self.model.body(i).name: self.data.xpos[i].copy()
            for i in range(1, self.model.nbody)
        }
        old_graph = (list(self.segments), list(self.links), list(self.tissues))
        old_contacts = self.contact_depths()
        old_model, old_data = self.model, self.data
        start = time.perf_counter()
        try:
            mutate()
            model, data = self.compile()
            self.transfer(model, data)
            self.model, self.data = model, data
            for pair, depth in self.contact_depths().items():
                if depth > max(0.001, old_contacts.get(pair, 0.0) + 1e-6):
                    raise ValueError("growth_intersects_scene")
            after = self.energy()
            added_mass = self.mass() - mass
            charge = (
                max(0.0, after - before)
                + max(0.0, added_mass) * self.config.growth_cost_per_kg
            )
            if (
                self.mass() > self.config.max_mass
                or self.spent + charge > self.config.energy_budget
            ):
                raise ValueError("material_or_energy_budget")
            continuity = max(
                float(np.linalg.norm(self.data.body(name).xpos - pos))
                for name, pos in poses.items()
            )
            if continuity > 1e-8:
                raise ValueError("edit_position_discontinuity")
            self.spent += charge
            self.growth_energy += after - before
            event = {
                "type": kind,
                "accepted": True,
                "time": float(data.time),
                **detail,
                "energy_before": before,
                "energy_after": after,
                "energy_delta": after - before,
                "added_mass": added_mass,
                "charge": charge,
                "position_error": continuity,
                "momentum_delta": (self.momentum() - momentum).tolist(),
                "material_supply": "External reservoir supplies material comoving with its attachment; its energy and momentum are logged.",
            }
            self.flex_reference = flex_reference_positions(model)
            for a in range(model.nu):
                self.muscle_reference.setdefault(
                    model.actuator(a).name, float(data.actuator_length[a])
                )
            self.previous_control = data.ctrl.copy()
        except (ValueError, RuntimeError) as exc:
            self.segments, self.links, self.tissues = old_graph
            self.model, self.data = old_model, old_data
            event = {
                "type": kind,
                "accepted": False,
                "time": float(self.data.time),
                **detail,
                "reason": str(exc),
            }
        elapsed = time.perf_counter() - start
        self.edit_seconds += elapsed
        event["wall_seconds"] = elapsed
        self.events.append(event)
        return event["accepted"]

    def grow(self, parent_id, module_id, direction):
        if len(self.segments) >= self.config.max_segments:
            return False
        parent = self.segments[parent_id]
        m = self.modules[module_id]
        quat = direction_quat(direction)
        local_rotation = Rotation.from_quat(np.roll(quat, -1)).as_matrix()
        start = self.data.site(f"tip{parent_id}").xpos.copy()
        rotation = self.data.body(f"s{parent_id}").xmat.reshape(3, 3)
        end = start + rotation @ local_rotation @ np.array([0, 0, m["length"]])
        reason = None
        if min(start[2], end[2]) < m["radius"] - 0.001:
            reason = "growth_intersects_floor"
        for s in self.segments:
            if s.id == parent_id:
                continue
            p, q = self.endpoints(s)
            candidate_start = start + (end - start) / m["length"] * min(
                m["radius"] * 2, m["length"] * 0.4
            )
            if s.parent is not None:
                p = p + (q - p) / s.length * min(s.radius * 2, s.length * 0.4)
            if (
                segment_distance(candidate_start, end, p, q)
                < s.radius + m["radius"] - 0.001
            ):
                reason = "growth_intersects_body"
        if reason:
            self.events.append(
                {
                    "type": "extend",
                    "accepted": False,
                    "time": float(self.data.time),
                    "parent": parent_id,
                    "reason": reason,
                }
            )
            return False
        s = Segment(
            len(self.segments),
            parent_id,
            module_id,
            m["length"],
            m["radius"],
            m["stiffness"],
            m["damping"],
            quat,
            float(self.data.time),
            parent.depth + 1,
        )
        return self.edit(
            "extend", lambda: self.segments.append(s), {"segment": asdict(s)}
        )

    def attach(self, a, b):
        if a == b or any({l.a, l.b} == {a, b} for l in self.links):
            return False
        pa, pb = self.positions()[[a, b]]
        # A physical cable may not be inserted through an existing body.
        for s in self.segments:
            if (
                s.id not in (a, b)
                and segment_distance(pa, pb, *self.endpoints(s)) < s.radius + 0.003
            ):
                return False
        link = Link(len(self.links), a, b, float(np.linalg.norm(pa - pb)))
        return self.edit(
            "attach", lambda: self.links.append(link), {"link": asdict(link)}
        )

    def add_tissue(self, segment):
        if segment in self.tissues or len(self.tissues) >= self.config.max_tissues:
            return False
        return self.edit(
            "tissue", lambda: self.tissues.append(segment), {"segment": segment}
        )

    def joint_strain(self, s):
        if s.parent is None:
            return 0.0
        q = self.data.joint(f"j{s.id}").qpos
        return 2 * math.acos(float(np.clip(abs(q[0]), 0, 1)))

    def contact_depths(self):
        depths = {}
        for contact in self.data.contact:
            names = []
            for i in range(2):
                geom = int(contact.geom[i])
                flex = int(contact.flex[i])
                names.append(
                    self.model.geom(geom).name
                    if geom >= 0
                    else f"flex:{mj.mj_id2name(self.model, mj.mjtObj.mjOBJ_FLEX, flex)}"
                )
            pair = tuple(sorted(names))
            depths[pair] = max(depths.get(pair, 0.0), -float(contact.dist))
        return depths

    def contact_segments(self):
        """Map solver-active contact to local owners, not mere proximity pairs.

        Tissue reports to its supporting segment; a link reports to both ends.
        Force-generating margins count, while gap/fused/passive contacts do not.
        """
        result = set()
        flex_owners = {f"tissue{s}": (s,) for s in self.tissues}
        flex_owners.update({f"link{l.id}": (l.a, l.b) for l in self.links})
        for contact in self.data.contact:
            if contact.exclude != 0 or contact.efc_address < 0:
                continue
            for geom, flex in zip(contact.geom, contact.flex):
                if geom >= 0:
                    name = self.model.geom(int(geom)).name
                    if name.startswith("g") and name[1:].isdigit():
                        result.add(int(name[1:]))
                elif flex >= 0:
                    name = mj.mj_id2name(self.model, mj.mjtObj.mjOBJ_FLEX, int(flex))
                    result.update(flex_owners.get(name, ()))
        return result

    def control(self):
        c, d = self.config, self.data
        contacts = self.contact_segments()
        for s in self.segments:
            if s.parent is None:
                continue
            m = self.modules[s.module]
            ramp = min(1.0, max(0.0, (d.time - s.born) / c.activation_ramp))
            feedback = (
                m["strain_gain"] * self.joint_strain(s)
                + m["contact_gain"] * (s.id in contacts)
                + m["signal_gain"] * s.signal
            )
            for k in range(3):
                a = self.model.actuator(f"muscle{s.id}_{k}").id
                phase = (
                    2 * math.pi * m["frequency"] * d.time
                    + m["phase"]
                    + k * 2 * math.pi / 3
                )
                activation = np.clip(
                    m["amplitude"] * (0.5 + 0.5 * math.sin(phase)) + feedback, 0, 1
                )
                force = c.muscle_force * activation * ramp
                tid = self.model.actuator_trnid[a, 0]
                speed = abs(d.ten_velocity[tid])
                force = min(force, c.muscle_power / max(speed, 1e-9))
                if (
                    speed > c.muscle_speed
                    or self.spent >= c.energy_budget
                    or d.actuator_length[a]
                    < c.muscle_min_fraction
                    * self.muscle_reference.get(self.model.actuator(a).name, 0.0)
                ):
                    force = 0.0
                d.ctrl[a] = -force
        self.previous_control = d.ctrl.copy()

    def step(self):
        c, d = self.config, self.data
        # Policy updates slowly; force, shortening, power and energy limits run every step.
        for a in range(self.model.nu):
            speed = abs(d.actuator_velocity[a])
            reference = self.muscle_reference.get(self.model.actuator(a).name, 0.0)
            enabled = (
                speed <= c.muscle_speed
                and d.actuator_length[a] >= c.muscle_min_fraction * reference
            )
            d.ctrl[a] = (
                -min(abs(self.previous_control[a]), c.muscle_power / max(speed, 1e-9))
                if enabled
                else 0.0
            )
        remaining = max(0.0, c.energy_budget - self.spent)
        reserve = c.timestep * (
            self.model.nu * c.muscle_power + float(sum(abs(d.ctrl))) * 0.001
        )
        if reserve > remaining:
            d.ctrl[:] *= remaining / max(reserve, 1e-15)
        old_velocity = d.qvel.copy()
        old_length = d.actuator_length.copy()
        state_type = mj.mjtState.mjSTATE_INTEGRATION
        checkpoint = np.empty(mj.mj_stateSize(self.model, state_type))
        mj.mj_getState(self.model, d, checkpoint, state_type)
        controls = d.ctrl.copy()
        for attempt in range(5):
            if attempt:
                mj.mj_setState(self.model, d, checkpoint, state_type)
                d.ctrl[:] = controls if attempt < 4 else 0.0
                mj.mj_forward(self.model, d)
            mj.mj_step(self.model, d)
            force = d.actuator_force.copy()
            external = (
                float(d.qfrc_applied @ (0.5 * (old_velocity + d.qvel))) * c.timestep
            )
            mj.mj_forward(self.model, d)
            # Constant motor force does work F * delta(length), including acceleration from rest.
            work_each = force * (d.actuator_length - old_length)
            supplied = float(np.maximum(work_each, 0).sum())
            charge = supplied + float(sum(abs(d.ctrl))) * 0.001 * c.timestep
            power_ratio = np.maximum(
                abs(work_each) / max(c.muscle_power * c.timestep, 1e-15), 1.0
            )
            average_speed = abs(d.actuator_length - old_length) / c.timestep
            over_speed = (average_speed > c.muscle_speed) & (abs(force) > 0)
            if np.any(over_speed):
                power_ratio[over_speed] = float("inf")
            if d.warning.number.any() or (
                charge <= remaining + 1e-12
                and np.max(power_ratio, initial=1.0) <= 1.0 + 1e-8
            ):
                break
            controls /= power_ratio
            controls *= min(1.0, remaining / max(charge, 1e-15)) * 0.95
        self.work += float(work_each.sum())
        self.positive_work += supplied
        self.external_work += external
        self.spent += charge
        if self.tissues:
            deformation = flex_deformation_metrics(self.model, d, self.flex_reference)
            self.tissue_min_volume = min(
                self.tissue_min_volume, deformation["min_volume_ratio"]
            )
            self.tissue_max_strain = max(
                self.tissue_max_strain, deformation["max_principal_green_strain"]
            )
        if d.ncon:
            self.max_contact_penetration = max(
                self.max_contact_penetration, max(0.0, -float(min(d.contact.dist)))
            )
        for contact in d.contact:
            if 0 in contact.geom:
                self.floor_contacts += 1
            elif all(
                g >= 0 and self.model.geom(int(g)).name.startswith("g")
                for g in contact.geom
            ):
                self.self_contacts += 1

    def validity(self):
        reasons = []
        if (
            not np.isfinite(self.data.qpos).all()
            or not np.isfinite(self.data.qvel).all()
        ):
            reasons.append("nonfinite_state")
        if np.max(np.abs(self.data.qvel), initial=0) > self.config.max_joint_speed:
            reasons.append("excessive_velocity")
        if np.max(np.abs(self.positions()), initial=0) > self.config.max_extent:
            reasons.append("escaped_domain")
        if self.max_contact_penetration > self.config.max_penetration:
            reasons.append("excessive_penetration")
        if self.data.warning.number.any():
            reasons.append("engine_warning")
        deformation = flex_deformation_metrics(
            self.model, self.data, self.flex_reference
        )
        if (
            deformation["inverted_elements"]
            or min(self.tissue_min_volume, deformation["min_volume_ratio"])
            < self.config.min_tissue_volume_ratio
        ):
            reasons.append("invalid_tissue_volume")
        if (
            max(self.tissue_max_strain, deformation["max_principal_green_strain"])
            > self.config.max_tissue_strain
        ):
            reasons.append("excessive_tissue_strain")
        if not math.isfinite(self.mass()) or self.mass() > self.config.max_mass:
            reasons.append("material_budget_exceeded")
        if self.spent > self.config.energy_budget + 1e-6:
            reasons.append("energy_budget_exceeded")
        return reasons

    def frame(self, phase):
        return {
            "time": float(self.data.time),
            "phase": phase,
            "segments": [
                {
                    "id": s.id,
                    "parent": s.parent,
                    "a": a.tolist(),
                    "b": b.tolist(),
                    "radius": s.radius,
                    "signal": s.signal,
                }
                for s in self.segments
                for a, b in (self.endpoints(s),)
            ],
            "links": [asdict(l) for l in self.links],
            "flex_vertices": self.data.flexvert_xpos.tolist(),
            "flex_elements": self.model.flex_elem.tolist(),
            "flexes": [
                {
                    "dim": int(self.model.flex_dim[f]),
                    "vertex_address": int(self.model.flex_vertadr[f]),
                    "vertex_count": int(self.model.flex_vertnum[f]),
                    "element_address": int(self.model.flex_elemdataadr[f]),
                    "element_count": int(self.model.flex_elemnum[f]),
                }
                for f in range(self.model.nflex)
            ],
            "object": self.data.body("object").xpos.tolist(),
            "energy": self.energy(),
            "spent": self.spent,
            "deformation": flex_deformation_metrics(
                self.model, self.data, self.flex_reference
            ),
            "qpos": self.data.qpos.tolist(),
            "qvel": self.data.qvel.tolist(),
        }
