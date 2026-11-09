package org.quantforge.core;

/** A failure with a contract error code. The CLI turns it into a result with status "error". */
public final class QfError extends RuntimeException {
    private static final long serialVersionUID = 1L;

    private final String code;
    private final String field;

    public QfError(String code, String message) {
        this(code, message, null);
    }

    public QfError(String code, String message, String field) {
        super(message, null, false, false);
        this.code = code;
        this.field = field;
    }

    public String code() {
        return code;
    }

    public String field() {
        return field;
    }
}
