// CLI handlers, stage H item H-21: paper trading (specifications/10-execution/paper-trading.md, HR-42 to HR-55;
// cli-contract.md "Stage H paper trading operations"). Simulated only: no handler reaches a network or a venue.
// Inputs are read in paper:: in the Python reference's order, so the error precedence matches.

void op_paper_book_apply_fill(const In& in, Out& out) {
    in.ready();
    paper::book_apply_fill(in.raw(), out.values);
}
void op_paper_book_end_of_day(const In& in, Out& out) {
    in.ready();
    paper::book_end_of_day(in.raw(), out.values);
}
void op_paper_pretrade_check(const In& in, Out& out) {
    in.ready();
    paper::pretrade_check(in.raw(), out.values);
}
void op_paper_ledger_append(const In& in, Out& out) {
    in.ready();
    paper::ledger_append(in.raw(), out.values);
}
void op_paper_ledger_verify(const In& in, Out& out) {
    in.ready();
    paper::ledger_verify(in.raw(), out.values);
}
void op_paper_session_run(const In& in, Out& out) {
    in.ready();
    paper::session_run(in.raw(), out.values);
}

constexpr Entry paper_ops[] = {
    {"paper.book.apply_fill", op_paper_book_apply_fill},
    {"paper.book.end_of_day", op_paper_book_end_of_day},
    {"paper.ledger.append", op_paper_ledger_append},
    {"paper.ledger.verify", op_paper_ledger_verify},
    {"paper.pretrade.check", op_paper_pretrade_check},
    {"paper.session.run", op_paper_session_run},
};
