-- RD repeat-detector, BF backfill, LN learn_now, T2 tuning, HR human review, T3 semantic
inductive W | RD | BF | LN | T2 | HR | T3 deriving DecidableEq, Repr

def all : List W := [.RD, .BF, .LN, .T2, .HR, .T3]
-- a must precede b: code import / data flow / rework if reversed
def edges : List (W × W) := [(.RD, .BF), (.BF, .LN), (.BF, .T2), (.LN, .T2), (.T2, .HR), (.HR, .T3)]
def order : List W := [.RD, .BF, .LN, .T2, .HR, .T3]
def pos (o : List W) (w : W) : Nat := o.idxOf w
def respects (o : List W) : Bool := edges.all (fun e => decide (pos o e.1 < pos o e.2))

-- all orderings, by fuel (structural, no sorry)
def permsF : Nat → List W → List (List W)
  | 0, _ => [[]]
  | n + 1, l => if l = [] then [[]] else l.flatMap (fun x => (permsF n (l.erase x)).map (x :: ·))
def perms (l : List W) := permsF l.length l

theorem order_respects : respects order = true := by decide +kernel
theorem backfill_first_breaks : respects [.BF, .RD, .LN, .T2, .HR, .T3] = false := by decide +kernel
theorem all_orderings_counted : (perms all).length = 720 := by decide +kernel
-- the dependency graph admits exactly one order: nothing to ask the user about
theorem order_is_forced : (perms all).filter respects = [order] := by decide +kernel

#print axioms order_is_forced
#print axioms backfill_first_breaks
