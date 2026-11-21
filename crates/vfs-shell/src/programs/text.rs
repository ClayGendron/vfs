//! The text programs: pure transforms of their input.

use super::Prog;
use crate::machine::Flow;

macro_rules! later {
    ($($name:ident),*) => {$(
        pub async fn $name(prog: &mut Prog<'_>, args: &[String]) -> Result<i32, Flow> {
            let _ = args;
            prog.err("not yet implemented").await?;
            Ok(1)
        }
    )*};
}
later!(cat, head, tail, wc, cut, sort, uniq, tr, tee);
