package org.quantforge.k3;

import io.aeron.Aeron;
import io.aeron.FragmentAssembler;
import io.aeron.Publication;
import io.aeron.Subscription;
import io.aeron.driver.MediaDriver;
import io.aeron.driver.ThreadingMode;
import io.aeron.logbuffer.FragmentHandler;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import org.agrona.concurrent.UnsafeBuffer;

/**
 * K-3 Aeron round trip (adapters.md 2.2). {@code sub ENDPOINT OUT N}: receive N messages and write them one per
 * line. {@code pub ENDPOINT IN N}: send the N lines of IN. Each process runs an embedded media driver; the stream
 * is reliable UDP unicast. Simulated; not a certified implementation; not connected to any venue.
 */
public final class AeronSmoke {
    private static final int STREAM = 1001;
    private static final long TIMEOUT_NS = 180_000_000_000L;

    private AeronSmoke() {}

    public static void main(String[] args) throws Exception {
        if (args.length != 4) {
            System.err.println("usage: AeronSmoke sub|pub ENDPOINT FILE N");
            System.exit(64);
        }
        String channel = "aeron:udp?endpoint=" + args[1] + "|term-length=1m";
        int n = Integer.parseInt(args[3]);
        MediaDriver.Context ctx = new MediaDriver.Context()
                .threadingMode(ThreadingMode.SHARED)
                .dirDeleteOnStart(true)
                .dirDeleteOnShutdown(true)
                .aeronDirectoryName(System.getProperty("k3.aeron.dir", "/dev/shm") + "/aeron-k3-" + args[0]);
        try (MediaDriver driver = MediaDriver.launchEmbedded(ctx);
             Aeron aeron = Aeron.connect(new Aeron.Context().aeronDirectoryName(driver.aeronDirectoryName()))) {
            int code = "sub".equals(args[0]) ? sub(aeron, channel, Path.of(args[2]), n) : pub(aeron, channel, Path.of(args[2]), n);
            System.exit(code);
        }
    }

    static int sub(Aeron aeron, String channel, Path out, int n) throws IOException {
        List<String> got = new ArrayList<>(n);
        FragmentHandler handler = new FragmentAssembler((buffer, offset, length, header) ->
                got.add(buffer.getStringWithoutLengthUtf8(offset, length)));
        try (Subscription sub = aeron.addSubscription(channel, STREAM)) {
            long deadline = System.nanoTime() + TIMEOUT_NS;
            while (got.size() < n && System.nanoTime() < deadline) {
                if (sub.poll(handler, 256) == 0) {
                    Thread.onSpinWait();
                }
            }
        }
        Files.writeString(out, String.join("\n", got) + (got.isEmpty() ? "" : "\n"), StandardCharsets.UTF_8);
        System.out.println("sub received " + got.size());
        return got.size() == n ? 0 : 1;
    }

    static int pub(Aeron aeron, String channel, Path in, int n) throws IOException, InterruptedException {
        List<String> lines = Files.readAllLines(in, StandardCharsets.UTF_8);
        if (lines.size() != n) {
            System.err.println("expected " + n + " lines, found " + lines.size());
            return 1;
        }
        UnsafeBuffer buf = new UnsafeBuffer(new byte[4096]);
        try (Publication pub = aeron.addPublication(channel, STREAM)) {
            long deadline = System.nanoTime() + TIMEOUT_NS;
            while (!pub.isConnected()) {
                if (System.nanoTime() > deadline) {
                    System.err.println("no subscriber connected");
                    return 1;
                }
                Thread.sleep(10);
            }
            for (String line : lines) {
                int len = buf.putStringWithoutLengthUtf8(0, line);
                long r;
                while ((r = pub.offer(buf, 0, len)) < 0) {
                    if (r == Publication.CLOSED || r == Publication.MAX_POSITION_EXCEEDED || System.nanoTime() > deadline) {
                        System.err.println("offer failed: " + r);
                        return 1;
                    }
                    Thread.onSpinWait();
                }
            }
            // Linger so the receiver can NAK and recover any lost datagram before the publication closes.
            Thread.sleep(3000);
        }
        System.out.println("pub sent " + n);
        return 0;
    }
}
