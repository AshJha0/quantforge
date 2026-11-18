# Stage H wave 2 blind extraction (extends the wave-1 Case/Input awk).
# Prints the spec text unchanged except markdown tables, where every column
# whose header is Expected, Derivation or Check is removed.
function trim(s){ gsub(/^[ \t]+|[ \t]+$/, "", s); return s }
/^\|/ {
  # An escaped pipe (backslash, pipe) inside a cell is text, not a column break (HR-77 in paper-trading.md).
  row = $0; gsub(/\\\|/, "\001", row)
  n = split(row, c, "|")
  if (!intable) {
    intable = 1; nk = 0
    for (i = 2; i < n; i++) { h = trim(c[i]); if (h != "Expected" && h != "Derivation" && h != "Check") keep[++nk] = i }
  }
  line = "|"
  for (j = 1; j <= nk; j++) line = line " " trim(c[keep[j]]) " |"
  gsub(/\001/, "\\|", line)
  print line; next
}
{ intable = 0; print }
