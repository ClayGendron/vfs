//! GNU `grep`.

use super::Prog;
use crate::machine::Flow;

pub async fn grep(prog: &mut Prog<'_>, args: &[String]) -> Result<i32, Flow> {
    let _ = args;
    prog.err("not yet implemented").await?;
    Ok(2)
}
