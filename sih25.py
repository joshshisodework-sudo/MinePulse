"""
SIH25025 - Underground Mine Seismic Monitoring Simulation
============================================================
A matplotlib-based interactive simulation of a dense sensor network
placed above an underground mine (a randomly generated footprint),
used to detect crack formation via vibration/tremor sensing and
Isolation Forest anomaly detection.

HOW TO RUN:
    python mine_crack_simulation.py

USAGE:
    - Pick a mine shape from the radio buttons in the top-left:
        * Round      - an organic, blobby open-pit-like footprint
        * Elongated  - a long, slim, randomly oriented footprint
        * Tree-like  - a randomly branching tunnel/seam network, like
                       a root system, with tapering corridor widths
      Picking a shape immediately regenerates the mine.
    - Click "Generate New Mine" at any time to redraw a brand new,
      randomly shaped mine footprint (in whichever mode is selected)
      with a fresh sensor grid inside it.
    - Click anywhere inside the mine outline to simulate a crack
      forming at that point underground.
    - A tremor radiates outward from the crack, decaying sharply with
      distance. ONLY nodes in the immediate vicinity of the crack can
      ever register a strong enough signal to be flagged - distant
      nodes physically can't "feel" it, no matter how noisy they are.
    - An Isolation Forest model (trained on normal background noise)
      flags nodes with abnormal readings as anomalies among the
      nearby candidates.
        * GREEN  node  -> normal background vibration
        * YELLOW node  -> in the buffer ring just outside the confirmed
                          anomaly - didn't trip the detector, but close
                          enough that a crack could plausibly extend
                          here too, worth watching
        * RED    node  -> anomaly detected in the immediate-contact
                          zone -> this region gets "cordoned off" with
                          a dashed red boundary
        * ORANGE star  -> the system's ESTIMATED crack epicenter,
                          triangulated from the red nodes' signal
                          strengths, with a realistic localization
                          offset applied (real sensor networks are
                          never pixel-perfect - there's always some
                          triangulation error)
    - A small black "x" marks the true (ground-truth) click location,
      just so you can visually compare it against the orange estimate.
    - Click multiple times to simulate new seismic events; the map
      resets and re-evaluates each time.

DEPENDENCIES:
    numpy, matplotlib, scikit-learn (scipy comes bundled with scikit-learn
    and is used here for the tree-mode tunnel geometry)
"""

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MplPolygon, Circle
from matplotlib.collections import PatchCollection
from matplotlib.path import Path
from matplotlib.widgets import Button, RadioButtons
from matplotlib.lines import Line2D
from scipy.spatial import ConvexHull
from sklearn.ensemble import IsolationForest

# ----------------------------------------------------------------------
# CONFIGURATION
# ----------------------------------------------------------------------
MINE_BASE_RADIUS = 5.5     # rough "radius" of a round mine before any stretching

# Fixed physical spacing between sensor nodes - this stays constant no
# matter how big/small/stretched the mine footprint is, since real
# sensor deployment density doesn't change with the shape you draw
# around it. Node COUNT will vary with mine area, not this spacing.
BASE_GRID_SPACING = 0.54
NODE_JITTER = 0.10         # small random offset so the grid doesn't look too robotic

# Elongated-mode stretch ranges: how much longer the long axis gets,
# and how much slimmer the short axis gets, relative to the base
# organic blob radius.
ELONGATE_STRETCH_LONG = (2.5, 4.2)
ELONGATE_STRETCH_SHORT = (1.8, 2.8)

# Tree-mode branching tunnel network parameters.
TREE_TRUNK_LENGTH = (3.0, 4.2)
TREE_TRUNK_RADIUS = (0.9, 1.3)     # half-width of the trunk corridor
TREE_TARGET_SEGMENTS = (28, 45)
TREE_BRANCH_ANGLE_DEG = 65         # max deviation angle per branch
TREE_LENGTH_SHRINK = (0.55, 0.85)  # each branch is this fraction of parent length
TREE_RADIUS_SHRINK = (0.60, 0.85)  # each branch is this fraction of parent radius
TREE_MIN_LENGTH = 0.9
TREE_MIN_RADIUS = max(0.35, BASE_GRID_SPACING * 0.8)

BASELINE_AMP_MEAN = 0.10   # normal background vibration amplitude
BASELINE_AMP_STD = 0.03
BASELINE_DUR_MEAN = 0.08   # normal background "signal duration" reading
BASELINE_DUR_STD = 0.03

CRACK_AMP_PEAK = 3.5       # peak amplitude right at the crack epicenter
CRACK_DUR_PEAK = 2.5       # peak duration reading right at the crack epicenter

N_BASELINE_TRAINING_SAMPLES = 500   # samples used to fit the Isolation Forest
CONTAMINATION = 0.06                # expected fraction of anomalies

AMP_DECAY_LENGTH = BASE_GRID_SPACING * 0.75    # sharp falloff -> localized signal
DUR_DECAY_LENGTH = BASE_GRID_SPACING * 0.65

# How many multiples of the node spacing count as "immediate contact".
# Nodes further than this from the crack are NEVER lit up red, regardless
# of noise or IsolationForest output - they simply can't feel it.
CONTACT_RADIUS_FACTOR = 1.7
CONTACT_RADIUS = BASE_GRID_SPACING * CONTACT_RADIUS_FACTOR

# Nodes beyond CONTACT_RADIUS but within WARNING_RADIUS turn yellow -
# a "this could crack too" buffer ring around the confirmed anomaly.
WARNING_RADIUS_FACTOR = 3.2
WARNING_RADIUS = BASE_GRID_SPACING * WARNING_RADIUS_FACTOR

# Real sensor triangulation is never pixel-perfect. We deliberately
# offset the estimated epicenter away from the true crack location by
# a random amount in this range (in grid-spacing units) so the
# detection doesn't look unrealistically precise.
LOCALIZATION_OFFSET_MIN = 0.6
LOCALIZATION_OFFSET_MAX = 1.6

SHAPE_MODES = ("Round", "Elongated", "Tree-like")

RNG = np.random.default_rng()   # no fixed seed -> a fresh random mine every run


# ----------------------------------------------------------------------
# TRAIN ISOLATION FOREST ON NORMAL (BASELINE) SEISMIC NOISE
# (independent of mine geometry, so this only needs to happen once)
# ----------------------------------------------------------------------
def generate_baseline_data(n_samples):
    amp = RNG.normal(BASELINE_AMP_MEAN, BASELINE_AMP_STD, n_samples)
    dur = RNG.normal(BASELINE_DUR_MEAN, BASELINE_DUR_STD, n_samples)
    return np.column_stack([amp, dur])


baseline_training_data = generate_baseline_data(N_BASELINE_TRAINING_SAMPLES)

iso_forest = IsolationForest(
    n_estimators=200,
    contamination=CONTAMINATION,
    random_state=42,
)
iso_forest.fit(baseline_training_data)


# ----------------------------------------------------------------------
# PLOTTING / INTERACTIVE APP
# ----------------------------------------------------------------------
class MineSimulation:
    def __init__(self):
        self.fig, self.ax = plt.subplots(figsize=(9, 9))
        self.fig.patch.set_facecolor("white")
        self.ax.set_facecolor("white")
        self.fig.subplots_adjust(bottom=0.14, top=0.86)

        self.ax.set_aspect("equal")
        self.fig.suptitle("Mine Seismic Monitoring Simulation", fontsize=13, fontweight="bold")
        self.ax.set_xticks([])
        self.ax.set_yticks([])

        self.shape_mode = "Round"

        # The mine footprint is always represented as a LIST of
        # matplotlib Paths - a single polygon for Round/Elongated, or
        # one capsule-shaped path per tunnel segment for Tree-like.
        # A point is "inside the mine" if it's inside ANY of them.
        self.mine_paths = []
        self.mine_patch = None     # PatchCollection drawing all of the above
        self.node_scatter = None
        self.click_marker = None       # ground-truth click marker
        self.epicenter_marker = None   # orange estimated-crack marker
        self.cordon_patch = None       # dashed red cordon circle

        self.nodes = None
        self.n_nodes = 0

        self._build_legend()

        # "Generate New Mine" button, top-right corner
        self.button_ax = self.fig.add_axes([0.72, 0.925, 0.24, 0.05])
        self.new_mine_button = Button(self.button_ax, "Generate New Mine",
                                       color="#f0f0f0", hovercolor="#dcdcdc")
        self.new_mine_button.on_clicked(self.on_new_mine_clicked)

        # Mine-shape selector, top-left corner
        self.mode_radio_ax = self.fig.add_axes([0.03, 0.885, 0.30, 0.11])
        self.mode_radio_ax.set_frame_on(False)
        self.mode_radio = RadioButtons(self.mode_radio_ax, SHAPE_MODES, active=0)
        self.mode_radio.on_clicked(self.on_mode_changed)

        self.regenerate_mine()
        self.fig.canvas.mpl_connect("button_press_event", self.on_click)

    # ------------------------------------------------------------
    # MINE GEOMETRY - shared helpers
    # ------------------------------------------------------------
    def _contains_points(self, points):
        """True for any point that falls inside ANY of the mine's paths."""
        points = np.atleast_2d(points)
        inside = np.zeros(len(points), dtype=bool)
        for path in self.mine_paths:
            inside |= path.contains_points(points)
        return inside

    def _contains_point(self, point):
        return bool(self._contains_points(np.array([point]))[0])

    def _bounds(self):
        all_verts = np.vstack([p.vertices for p in self.mine_paths])
        xmin, ymin = all_verts.min(axis=0)
        xmax, ymax = all_verts.max(axis=0)
        margin = max(1.2, 0.08 * max(xmax - xmin, ymax - ymin))
        return (xmin - margin, xmax + margin, ymin - margin, ymax + margin)

    # ------------------------------------------------------------
    # MINE GEOMETRY - Round / Elongated (organic blob polygon)
    # ------------------------------------------------------------
    def _generate_blob_polygon(self, elongated, base_radius=MINE_BASE_RADIUS,
                                n_points=240, n_harmonics=5):
        """Builds an irregular closed polygon (in polar form) by summing a
        few random sinusoidal harmonics on top of a base radius - this
        gives a smooth, organic, cave/pit-like outline. Centered at the
        origin; regenerate_mine() repositions the view around it.

        In elongated mode, the resulting blob is stretched along one
        axis and squeezed along the other, then rotated to a random
        orientation, producing a long, slim, seam/tunnel-like footprint
        instead of a round open-pit-like footprint."""
        theta = np.linspace(0, 2 * np.pi, n_points, endpoint=False)
        r = np.full_like(theta, base_radius)
        for k in range(1, n_harmonics + 1):
            amplitude = RNG.uniform(0.05, 0.30) * base_radius / k
            phase = RNG.uniform(0, 2 * np.pi)
            r += amplitude * np.sin(k * theta + phase)
        r = np.clip(r, base_radius * 0.35, base_radius * 1.25)

        x = r * np.cos(theta)
        y = r * np.sin(theta)

        if elongated:
            stretch_long = RNG.uniform(*ELONGATE_STRETCH_LONG)
            stretch_short = RNG.uniform(*ELONGATE_STRETCH_SHORT)
            x *= stretch_long
            y /= stretch_short

            angle = RNG.uniform(0, 2 * np.pi)
            cos_a, sin_a = np.cos(angle), np.sin(angle)
            x_rot = x * cos_a - y * sin_a
            y_rot = x * sin_a + y * cos_a
            x, y = x_rot, y_rot

        return np.column_stack([x, y])

    # ------------------------------------------------------------
    # MINE GEOMETRY - Tree-like (branching tunnel network)
    # ------------------------------------------------------------
    def _generate_tree_segments(self):
        """Grows a random branching network of tunnel segments, each a
        (start, end, half_width) tuple, starting from a single trunk
        and repeatedly forking with shrinking length/width - similar
        in spirit to a simple L-system / root-growth model."""
        segments = []
        root = np.zeros(2)
        angle = RNG.uniform(0, 2 * np.pi)
        length = RNG.uniform(*TREE_TRUNK_LENGTH)
        radius = RNG.uniform(*TREE_TRUNK_RADIUS)
        target_segments = RNG.integers(*TREE_TARGET_SEGMENTS)

        frontier = [(root, angle, length, radius)]
        while frontier and len(segments) < target_segments:
            p, ang, length, radius = frontier.pop(0)
            end = p + length * np.array([np.cos(ang), np.sin(ang)])
            segments.append((p, end, radius))

            if len(segments) >= target_segments:
                break
            if length < TREE_MIN_LENGTH or radius < TREE_MIN_RADIUS:
                continue

            if len(segments) <= 2:
                n_branches = int(RNG.integers(2, 4))   # force early forking
            else:
                n_branches = int(RNG.choice([1, 2, 3], p=[0.45, 0.45, 0.10]))

            for _ in range(n_branches):
                delta = np.deg2rad(RNG.uniform(-TREE_BRANCH_ANGLE_DEG, TREE_BRANCH_ANGLE_DEG))
                new_angle = ang + delta
                new_length = length * RNG.uniform(*TREE_LENGTH_SHRINK)
                new_radius = max(radius * RNG.uniform(*TREE_RADIUS_SHRINK), TREE_MIN_RADIUS * 0.9)
                frontier.append((end, new_angle, new_length, new_radius))

        return segments

    def _capsule_path(self, a, b, r, n_circle=14):
        """A 'stadium' shape (rectangle + two semicircular caps) around
        segment a->b with half-width r. Since both end-caps share the
        same radius, this shape is convex, so we can build it simply by
        taking the convex hull of two full circles at a and b."""
        theta = np.linspace(0, 2 * np.pi, n_circle, endpoint=False)
        circle = np.column_stack([np.cos(theta), np.sin(theta)]) * r
        pts = np.vstack([circle + a, circle + b])
        hull = ConvexHull(pts)
        return Path(pts[hull.vertices])

    def _generate_tree_paths(self):
        segments = self._generate_tree_segments()
        return [self._capsule_path(a, b, r) for a, b, r in segments]

    # ------------------------------------------------------------
    # NODE GRID
    # ------------------------------------------------------------
    def _build_node_grid(self, bounds):
        xmin, xmax, ymin, ymax = bounds
        nx = int(np.ceil((xmax - xmin) / BASE_GRID_SPACING)) + 2
        ny = int(np.ceil((ymax - ymin) / BASE_GRID_SPACING)) + 2
        xs = np.linspace(xmin, xmax, max(nx, 2))
        ys = np.linspace(ymin, ymax, max(ny, 2))
        xx, yy = np.meshgrid(xs, ys)
        candidates = np.column_stack([xx.ravel(), yy.ravel()])
        candidates = candidates + RNG.uniform(-NODE_JITTER, NODE_JITTER, candidates.shape)
        inside = self._contains_points(candidates)
        return candidates[inside]

    # ------------------------------------------------------------
    # MINE (RE)GENERATION
    # ------------------------------------------------------------
    def regenerate_mine(self):
        """(Re)generates the mine footprint and sensor grid, and redraws
        everything on the axes. Used on first load, whenever the
        'Generate New Mine' button is clicked, and whenever the shape
        mode is changed."""
        self.clear_previous_event()

        if self.mine_patch is not None:
            self.mine_patch.remove()
        if self.node_scatter is not None:
            self.node_scatter.remove()

        if self.shape_mode == "Tree-like":
            self.mine_paths = self._generate_tree_paths()
        else:
            polygon = self._generate_blob_polygon(elongated=(self.shape_mode == "Elongated"))
            self.mine_paths = [Path(polygon)]

        bounds = self._bounds()
        self.ax.set_xlim(bounds[0], bounds[1])
        self.ax.set_ylim(bounds[2], bounds[3])

        self.nodes = self._build_node_grid(bounds)
        self.n_nodes = len(self.nodes)

        patches = [MplPolygon(p.vertices, closed=True) for p in self.mine_paths]
        self.mine_patch = PatchCollection(
            patches, facecolor="#e8dcc8", edgecolor="#a68a5b", linewidths=1.4, zorder=0,
        )
        self.ax.add_collection(self.mine_patch)

        self.node_scatter = self.ax.scatter(
            self.nodes[:, 0], self.nodes[:, 1],
            c="green", s=40, edgecolors="black", linewidths=0.4, zorder=3,
        )

        self.ax.set_title(
            f"New {self.shape_mode.lower()} mine generated ({self.n_nodes} sensor nodes) - "
            f"click inside the outline to simulate a crack",
            fontsize=10,
        )
        self.fig.canvas.draw_idle()

    def on_new_mine_clicked(self, event):
        self.regenerate_mine()

    def on_mode_changed(self, label):
        self.shape_mode = label
        self.regenerate_mine()

    # ------------------------------------------------------------
    # LEGEND
    # ------------------------------------------------------------
    def _build_legend(self):
        legend_elems = [
            Line2D([0], [0], marker="o", color="w", label="Normal node",
                   markerfacecolor="green", markeredgecolor="black", markersize=9),
            Line2D([0], [0], marker="o", color="w", label="Buffer zone (possible crack)",
                   markerfacecolor="yellow", markeredgecolor="black", markersize=9),
            Line2D([0], [0], marker="o", color="w", label="Anomalous node (cordon)",
                   markerfacecolor="red", markeredgecolor="black", markersize=9),
            Line2D([0], [0], marker="*", color="w", label="Estimated crack (from sensors)",
                   markerfacecolor="orange", markeredgecolor="black", markersize=14),
            Line2D([0], [0], marker="x", color="black", label="True crack (ground truth)",
                   markersize=9, linestyle="None"),
        ]
        self.ax.legend(handles=legend_elems, loc="upper center",
                        bbox_to_anchor=(0.5, -0.04), ncol=3, frameon=False, fontsize=9)

    # ------------------------------------------------------------
    # CRACK SIMULATION
    # ------------------------------------------------------------
    def simulate_crack(self, crack_xy):
        """Given a crack location, compute each node's (amplitude, duration)
        reading based on sharp distance-decay + noise, run Isolation Forest
        to flag anomalous readings, then hard-clip: only nodes within the
        immediate-contact radius are allowed to be flagged red at all."""
        dists = np.linalg.norm(self.nodes - np.array(crack_xy), axis=1)

        amp_signal = CRACK_AMP_PEAK * np.exp(-dists / AMP_DECAY_LENGTH)
        dur_signal = CRACK_DUR_PEAK * np.exp(-dists / DUR_DECAY_LENGTH)

        amp_noise = RNG.normal(BASELINE_AMP_MEAN, BASELINE_AMP_STD, self.n_nodes)
        dur_noise = RNG.normal(BASELINE_DUR_MEAN, BASELINE_DUR_STD, self.n_nodes)

        amplitude = amp_signal + amp_noise
        duration = dur_signal + dur_noise

        features = np.column_stack([amplitude, duration])
        predictions = iso_forest.predict(features)   # -1 = anomaly, 1 = normal

        # Hard physical constraint: nodes outside the immediate-contact
        # radius cannot be flagged, no matter what the model says.
        predictions = np.where(dists > CONTACT_RADIUS, 1, predictions)

        return amplitude, duration, predictions, dists

    def estimate_epicenter(self, anomalous_nodes, weights):
        """Weighted centroid of the flagged (red) nodes, weighted by how
        strong their vibration reading was, PLUS a random offset to
        simulate realistic triangulation error - real sensor networks
        never pinpoint a crack with pixel-perfect accuracy."""
        if len(anomalous_nodes) == 0:
            return None
        w = weights / weights.sum()
        est_x = np.sum(anomalous_nodes[:, 0] * w)
        est_y = np.sum(anomalous_nodes[:, 1] * w)

        offset_mag = RNG.uniform(LOCALIZATION_OFFSET_MIN, LOCALIZATION_OFFSET_MAX) * BASE_GRID_SPACING
        offset_angle = RNG.uniform(0, 2 * np.pi)
        est_x += offset_mag * np.cos(offset_angle)
        est_y += offset_mag * np.sin(offset_angle)
        return est_x, est_y

    # ------------------------------------------------------------
    # EVENT HANDLING
    # ------------------------------------------------------------
    def clear_previous_event(self):
        if self.click_marker is not None:
            self.click_marker.remove()
            self.click_marker = None
        if self.epicenter_marker is not None:
            self.epicenter_marker.remove()
            self.epicenter_marker = None
        if self.cordon_patch is not None:
            self.cordon_patch.remove()
            self.cordon_patch = None

    def on_click(self, event):
        if event.inaxes != self.ax:
            return
        if event.xdata is None or event.ydata is None:
            return

        crack_xy = (event.xdata, event.ydata)

        if not self._contains_point(crack_xy):
            self.ax.set_title(
                "Click was outside the mine footprint - ignored.",
                fontsize=10, color="gray",
            )
            self.fig.canvas.draw_idle()
            return

        self.clear_previous_event()

        amplitude, duration, predictions, dists = self.simulate_crack(crack_xy)
        is_anomaly = predictions == -1
        is_warning = (~is_anomaly) & (dists <= WARNING_RADIUS)

        # Layer the colors: green by default, yellow buffer ring, red core
        colors = np.full(self.n_nodes, "green", dtype=object)
        colors[is_warning] = "yellow"
        colors[is_anomaly] = "red"
        self.node_scatter.set_color(colors)

        # Mark the true click location (ground truth) with a black x
        self.click_marker = self.ax.scatter(
            [crack_xy[0]], [crack_xy[1]], c="black", marker="x", s=90, zorder=5,
        )

        n_flagged = int(is_anomaly.sum())
        n_warning = int(is_warning.sum())

        if n_flagged > 0:
            red_nodes = self.nodes[is_anomaly]
            red_weights = amplitude[is_anomaly]

            est_x, est_y = self.estimate_epicenter(red_nodes, red_weights)
            self.epicenter_marker = self.ax.scatter(
                [est_x], [est_y], c="orange", marker="*", s=300,
                edgecolors="black", zorder=6,
            )

            # Draw a dashed "cordon" circle around the flagged cluster,
            # padded out a bit further since the estimate itself can now
            # sit slightly outside the tight core.
            radial_dists = np.linalg.norm(red_nodes - np.array([est_x, est_y]), axis=1)
            cordon_radius = max(radial_dists.max() + 0.5, CONTACT_RADIUS * 0.9)
            self.cordon_patch = Circle(
                (est_x, est_y), cordon_radius,
                fill=False, edgecolor="red", linestyle="--", linewidth=2, zorder=4,
            )
            self.ax.add_patch(self.cordon_patch)

            error = np.hypot(est_x - crack_xy[0], est_y - crack_xy[1])
            self.ax.set_title(
                f"CRACK DETECTED - {n_flagged} node(s) flagged, {n_warning} in buffer zone - "
                f"cordoned off (localization error: {error:.2f} units)",
                fontsize=10, color="firebrick",
            )
        else:
            self.ax.set_title(
                "No nearby nodes picked up a strong enough signal - no anomaly flagged.",
                fontsize=10, color="black",
            )

        self.fig.canvas.draw_idle()


def main():
    sim = MineSimulation()
    plt.show()


if __name__ == "__main__":
    main()
