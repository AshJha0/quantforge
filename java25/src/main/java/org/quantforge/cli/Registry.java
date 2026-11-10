package org.quantforge.cli;

import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.function.Consumer;
import java.util.function.Function;
import org.quantforge.cli.Operations.Out;

/**
 * The operation registry. Each domain module registers its verbs; the CLI dispatches and lists verbs only from here,
 * so the verb table is generated from the registry. A verb registered twice is a build fault.
 */
final class Registry {
    /** A domain module: its name and the routine that adds its verbs to a table. */
    record Module(String domain, Consumer<Map<String, Function<In, Out>>> register) {}

    private final Map<String, Function<In, Out>> handlers;
    private final Map<String, String> domains;

    private Registry(Map<String, Function<In, Out>> handlers, Map<String, String> domains) {
        this.handlers = Collections.unmodifiableMap(handlers);
        this.domains = Collections.unmodifiableMap(domains);
    }

    static Registry of(List<Module> modules) {
        Map<String, Function<In, Out>> handlers = new TreeMap<>();
        Map<String, String> domains = new TreeMap<>();
        Set<String> seen = new java.util.HashSet<>();
        for (Module m : modules) {
            if (!seen.add(m.domain())) {
                throw new IllegalStateException("module registered twice: " + m.domain());
            }
            Map<String, Function<In, Out>> part = new LinkedHashMap<>();
            m.register().accept(part);
            for (var e : part.entrySet()) {
                if (handlers.putIfAbsent(e.getKey(), e.getValue()) != null) {
                    throw new IllegalStateException("operation " + e.getKey() + " registered by " + domains.get(e.getKey())
                            + " and " + m.domain());
                }
                domains.put(e.getKey(), m.domain());
            }
        }
        return new Registry(handlers, domains);
    }

    /** Verb names in sorted order. */
    Set<String> names() {
        return handlers.keySet();
    }

    Function<In, Out> find(String name) {
        return handlers.get(name);
    }

    /** The verb table: each verb and the domain module that owns it, sorted by verb. */
    Map<String, String> table() {
        return domains;
    }
}
