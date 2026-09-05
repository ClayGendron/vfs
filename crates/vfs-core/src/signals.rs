//! The centrality prior: a link measure over a reference graph, `log1p`-
//! transformed, smoothed through the containing hierarchy, and min-max
//! scaled over the retrievable nodes.
//!
//! Nodes are dense indices the host assigns. `sources`/`targets` are the
//! reference edges — never the hierarchy — `parents[i]` is node `i`'s
//! containing directory (or [`NO_PARENT`] at a root) and `files[i]` says
//! whether the node is retrievable. The tree is read for smoothing only:
//! each directory takes the mean of its files' transformed measure and
//! its subdirectories' means (bottom-up), then every node blends its own
//! value with its parent's prior, `p = (1 − γ)·own + γ·p(parent)`
//! (top-down). Only files are scaled and reported; a directory's slot
//! reads `0.0`. Accumulation order is fixed by edge order and node
//! index, so an answer is bit-reproducible.

/// The parent slot of a node with no containing directory.
pub const NO_PARENT: i64 = -1;

/// The raw link measure the prior starts from.
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Measure {
    /// Incoming reference edges, counted.
    InDegree,
    /// Power-iterated PageRank, dangling mass spread uniformly, scaled
    /// by the node count so the mean rank is one.
    PageRank { damping: f64, iterations: u32 },
    /// Katz centrality `Σ αᵏ·(Aᵀ)ᵏ·1` less the node's own unit, so a node
    /// nothing refers to measures zero like an in-degree of zero.
    Katz { alpha: f64, iterations: u32 },
}

#[derive(Debug, PartialEq, Eq)]
pub enum SignalError {
    EdgeShape { sources: usize, targets: usize },
    TreeShape { parents: usize, files: usize, node_count: usize },
    NodeOutOfRange { index: i64, node_count: usize },
    TreeCycle { node: usize },
    Parameter(&'static str),
}

impl std::fmt::Display for SignalError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::EdgeShape { sources, targets } => {
                write!(f, "edge arrays disagree: {sources} sources, {targets} targets")
            }
            Self::TreeShape { parents, files, node_count } => {
                write!(f, "tree arrays disagree with {node_count} nodes: {parents} parents, {files} file flags")
            }
            Self::NodeOutOfRange { index, node_count } => {
                write!(f, "node index {index} is outside the {node_count} nodes")
            }
            Self::TreeCycle { node } => write!(f, "the parent chain from node {node} is a cycle"),
            Self::Parameter(what) => write!(f, "{what}"),
        }
    }
}

impl std::error::Error for SignalError {}

// ---------------------------------------------------------------------------
// The prior
// ---------------------------------------------------------------------------

/// The prior per node: `0.0` for directories, `[0, 1]` for files.
///
/// Refused: edge or tree arrays of the wrong length, a node index at or
/// past `node_count`, a parent chain that loops, a `gamma` outside
/// `[0, 1]`, a PageRank damping outside `(0, 1)`, a Katz alpha that is
/// not positive, or zero iterations.
pub fn centrality_prior(
    node_count: usize,
    sources: &[i64],
    targets: &[i64],
    parents: &[i64],
    files: &[bool],
    measure: Measure,
    gamma: f64,
) -> Result<Vec<f64>, SignalError> {
    if sources.len() != targets.len() {
        return Err(SignalError::EdgeShape { sources: sources.len(), targets: targets.len() });
    }
    if parents.len() != node_count || files.len() != node_count {
        return Err(SignalError::TreeShape { parents: parents.len(), files: files.len(), node_count });
    }
    if !(0.0..=1.0).contains(&gamma) {
        return Err(SignalError::Parameter("gamma must lie in [0, 1]"));
    }
    let edges = dense_edges(node_count, sources, targets)?;
    let depth = depths(parents, node_count)?;
    let raw = match measure {
        Measure::InDegree => in_degree(node_count, &edges),
        Measure::PageRank { damping, iterations } => {
            if !(damping > 0.0 && damping < 1.0) {
                return Err(SignalError::Parameter("PageRank damping must lie in (0, 1)"));
            }
            if iterations == 0 {
                return Err(SignalError::Parameter("iterations must be at least 1"));
            }
            pagerank(node_count, &edges, damping, iterations)
        }
        Measure::Katz { alpha, iterations } => {
            if !(alpha > 0.0 && alpha.is_finite()) {
                return Err(SignalError::Parameter("Katz alpha must be positive"));
            }
            if iterations == 0 {
                return Err(SignalError::Parameter("iterations must be at least 1"));
            }
            katz(node_count, &edges, alpha, iterations)
        }
    };
    let measured: Vec<f64> = raw.iter().map(|value| value.ln_1p()).collect();
    let prior = smooth(&measured, parents, files, &depth, gamma);
    Ok(scale_files(&prior, files))
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

/// Edges as `(source, target)` node indices, each checked against the node count.
fn dense_edges(node_count: usize, sources: &[i64], targets: &[i64]) -> Result<Vec<(usize, usize)>, SignalError> {
    let index = |raw: i64| -> Result<usize, SignalError> {
        usize::try_from(raw)
            .ok()
            .filter(|&index| index < node_count)
            .ok_or(SignalError::NodeOutOfRange { index: raw, node_count })
    };
    sources.iter().zip(targets).map(|(&s, &t)| Ok((index(s)?, index(t)?))).collect()
}

/// Each node's depth from its root; a parent outside the nodes or a looping chain is refused.
fn depths(parents: &[i64], node_count: usize) -> Result<Vec<u32>, SignalError> {
    const UNSEEN: u32 = u32::MAX;
    const WALKING: u32 = u32::MAX - 1;
    let mut depth = vec![UNSEEN; node_count];
    let mut path = Vec::new();
    for start in 0..node_count {
        if depth[start] != UNSEEN {
            continue;
        }
        path.clear();
        let mut node = start;
        let base = loop {
            match depth[node] {
                WALKING => return Err(SignalError::TreeCycle { node: start }),
                UNSEEN => {}
                known => break known + 1,
            }
            depth[node] = WALKING;
            path.push(node);
            match parents[node] {
                NO_PARENT => break 0,
                parent => {
                    node = usize::try_from(parent)
                        .ok()
                        .filter(|&index| index < node_count)
                        .ok_or(SignalError::NodeOutOfRange { index: parent, node_count })?;
                }
            }
        };
        // `path` runs child-ward from `start`; the last pushed node sits at `base`.
        for (steps, &walked) in path.iter().rev().enumerate() {
            depth[walked] = base + steps as u32;
        }
    }
    Ok(depth)
}

fn in_degree(node_count: usize, edges: &[(usize, usize)]) -> Vec<f64> {
    let mut degree = vec![0.0; node_count];
    for &(_, target) in edges {
        degree[target] += 1.0;
    }
    degree
}

fn pagerank(node_count: usize, edges: &[(usize, usize)], damping: f64, iterations: u32) -> Vec<f64> {
    let count = node_count as f64;
    let mut out_degree = vec![0.0; node_count];
    for &(source, _) in edges {
        out_degree[source] += 1.0;
    }
    let mut rank = vec![1.0 / count; node_count];
    for _ in 0..iterations {
        let dangling: f64 = (0..node_count).filter(|&node| out_degree[node] == 0.0).map(|node| rank[node]).sum();
        let base = ((1.0 - damping) + damping * dangling) / count;
        let mut next = vec![base; node_count];
        for &(source, target) in edges {
            next[target] += damping * rank[source] / out_degree[source];
        }
        rank = next;
    }
    rank.iter().map(|value| value * count).collect()
}

fn katz(node_count: usize, edges: &[(usize, usize)], alpha: f64, iterations: u32) -> Vec<f64> {
    let mut score = vec![0.0; node_count];
    for _ in 0..iterations {
        let mut next = vec![1.0; node_count];
        for &(source, target) in edges {
            next[target] += alpha * score[source];
        }
        score = next;
    }
    score.iter().map(|value| value - 1.0).collect()
}

/// The two tree passes: directory means bottom-up, then the parent blend top-down.
///
/// A directory with nothing under it has no mean and adds nothing to
/// its parent's; a root blends with nothing.
fn smooth(measured: &[f64], parents: &[i64], files: &[bool], depth: &[u32], gamma: f64) -> Vec<f64> {
    let node_count = measured.len();
    let mut order: Vec<usize> = (0..node_count).collect();
    order.sort_by_key(|&node| depth[node]);
    let mut sum = vec![0.0; node_count];
    let mut count = vec![0usize; node_count];
    let mut own = vec![0.0; node_count];
    for &node in order.iter().rev() {
        let (value, counted) = if files[node] {
            (measured[node], true)
        } else if count[node] > 0 {
            (sum[node] / count[node] as f64, true)
        } else {
            (0.0, false)
        };
        own[node] = value;
        if counted && parents[node] != NO_PARENT {
            let parent = parents[node] as usize;
            sum[parent] += value;
            count[parent] += 1;
        }
    }
    let mut prior = vec![0.0; node_count];
    for &node in &order {
        prior[node] = match parents[node] {
            NO_PARENT => own[node],
            parent => (1.0 - gamma) * own[node] + gamma * prior[parent as usize],
        };
    }
    prior
}

/// Files scaled to `[0, 1]` over their own range — all equal, or none, scales to zero; directories read zero.
fn scale_files(prior: &[f64], files: &[bool]) -> Vec<f64> {
    let mut low = f64::INFINITY;
    let mut high = f64::NEG_INFINITY;
    for (value, &file) in prior.iter().zip(files) {
        if file {
            low = low.min(*value);
            high = high.max(*value);
        }
    }
    let span = high - low;
    prior
        .iter()
        .zip(files)
        .map(|(value, &file)| if file && span > 0.0 { (value - low) / span } else { 0.0 })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    // Nodes: 0 = root dir, 1 = dir a, 2 = file a/x, 3 = file a/y, 4 = file z.
    const PARENTS: [i64; 5] = [NO_PARENT, 0, 1, 1, 0];
    const FILES: [bool; 5] = [false, false, true, true, true];

    #[test]
    fn in_degree_with_no_smoothing_is_the_scaled_log_count() {
        // x referenced twice, y once, z never.
        let prior = centrality_prior(5, &[3, 4, 4], &[2, 2, 3], &PARENTS, &FILES, Measure::InDegree, 0.0).unwrap();
        assert_eq!(prior[0], 0.0);
        assert_eq!(prior[1], 0.0);
        assert_eq!(prior[2], 1.0);
        assert!((prior[3] - 2f64.ln() / 3f64.ln()).abs() < 1e-12);
        assert_eq!(prior[4], 0.0);
    }

    #[test]
    fn smoothing_lifts_a_file_by_its_directory() {
        // Only x is referenced; y inherits a share of a's mean through gamma.
        let prior = centrality_prior(5, &[4], &[2], &PARENTS, &FILES, Measure::InDegree, 0.2).unwrap();
        assert_eq!(prior[2], 1.0);
        assert!(prior[3] > 0.0 && prior[3] < prior[2]);
        assert_eq!(prior[4], 0.0);
    }

    #[test]
    fn a_uniform_measure_scales_to_zero_everywhere() {
        let prior = centrality_prior(5, &[], &[], &PARENTS, &FILES, Measure::InDegree, 0.2).unwrap();
        assert!(prior.iter().all(|&value| value == 0.0));
    }

    #[test]
    fn pagerank_ranks_the_referenced_file_first() {
        let prior =
            centrality_prior(5, &[3, 4], &[2, 2], &PARENTS, &FILES, Measure::PageRank { damping: 0.85, iterations: 20 }, 0.0)
                .unwrap();
        assert_eq!(prior[2], 1.0);
        assert!(prior[3] < 1.0 && prior[4] < 1.0);
    }

    #[test]
    fn katz_counts_paths_of_every_length() {
        // z -> y -> x: x gains from both the direct and the two-step path.
        let prior =
            centrality_prior(5, &[4, 3], &[3, 2], &PARENTS, &FILES, Measure::Katz { alpha: 0.5, iterations: 10 }, 0.0).unwrap();
        assert_eq!(prior[2], 1.0);
        assert!(prior[3] > 0.0 && prior[3] < 1.0);
        assert_eq!(prior[4], 0.0);
    }

    #[test]
    fn shapes_and_parameters_are_refused() {
        assert_eq!(
            centrality_prior(5, &[1], &[], &PARENTS, &FILES, Measure::InDegree, 0.0),
            Err(SignalError::EdgeShape { sources: 1, targets: 0 })
        );
        assert_eq!(
            centrality_prior(4, &[], &[], &PARENTS, &FILES, Measure::InDegree, 0.0),
            Err(SignalError::TreeShape { parents: 5, files: 5, node_count: 4 })
        );
        assert_eq!(
            centrality_prior(5, &[7], &[2], &PARENTS, &FILES, Measure::InDegree, 0.0),
            Err(SignalError::NodeOutOfRange { index: 7, node_count: 5 })
        );
        assert_eq!(
            centrality_prior(2, &[], &[], &[1, 0], &[true, true], Measure::InDegree, 0.0),
            Err(SignalError::TreeCycle { node: 0 })
        );
        assert!(centrality_prior(5, &[], &[], &PARENTS, &FILES, Measure::InDegree, 1.5).is_err());
        assert!(centrality_prior(5, &[], &[], &PARENTS, &FILES, Measure::PageRank { damping: 1.0, iterations: 1 }, 0.0).is_err());
        assert!(centrality_prior(5, &[], &[], &PARENTS, &FILES, Measure::Katz { alpha: 0.1, iterations: 0 }, 0.0).is_err());
    }
}
