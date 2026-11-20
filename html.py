<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
    body {
        margin: 0;
        font-family: Arial, sans-serif;
        color: #17345e;
    }

    .safety-panel {
        padding: 13px;
        border: 1px solid #d8e2ef;
        border-radius: 12px;
        background: #f5f8fc;
    }

    .safety-title {
        font-weight: bold;
        font-size: 15px;
        margin-bottom: 6px;
    }

    .safety-status {
        font-size: 13px;
        margin-bottom: 10px;
    }

    button {
        border: 0;
        border-radius: 8px;
        padding: 9px 13px;
        background: #17345e;
        color: white;
        cursor: pointer;
        font-weight: bold;
    }

    .warning {
        color: #b42318;
        font-weight: bold;
    }
</style>
</head>

<body>

<div class="safety-panel">
    <div class="safety-title">🛡️ MISKONSEPTION — Pengawasan Ujian</div>
    <div id="status" class="safety-status">
        Menyiapkan pemantauan ujian...
    </div>
    <div id="counter" class="safety-status">
        Pelanggaran: 0 dari 3
    </div>
    <button id="fullscreenButton">
        Aktifkan Layar Penuh
    </button>
</div>

<script>
(function () {
    const statusEl = document.getElementById("status");
    const counterEl = document.getElementById("counter");
    const fullscreenButton = document.getElementById("fullscreenButton");

    let strikeCount = 0;
    let examActive = false;
    let pendingEvent = false;
    let lastEventId = null;
    let lastProcessedEventId = null;
    let lastVisibilityEvent = 0;

    function sendToStreamlit(type, description) {
        if (!examActive || pendingEvent || strikeCount >= 3) {
            return;
        }

        const now = Date.now();

        // Menghindari satu kejadian tercatat berulang kali
        if (now - lastVisibilityEvent < 1200) {
            return;
        }

        lastVisibilityEvent = now;
        pendingEvent = true;

        lastEventId = (
            "evt-" + now + "-" +
            Math.random().toString(36).substring(2, 10)
        );

        playWarning();

        statusEl.innerHTML =
            '<span class="warning">Peringatan: aktivitas ujian terdeteksi.</span>';

        window.parent.postMessage({
            isStreamlitMessage: true,
            type: "streamlit:setComponentValue",
            value: {
                event_id: lastEventId,
                violation_type: type,
                description: description,
                event_time: new Date().toISOString()
            },
            dataType: "json"
        }, "*");
    }

    function playWarning() {
        try {
            const AudioContext =
                window.AudioContext || window.webkitAudioContext;

            if (!AudioContext) return;

            const audio = new AudioContext();

            if (audio.state === "suspended") {
                audio.resume();
            }

            const oscillator = audio.createOscillator();
            const gain = audio.createGain();

            oscillator.connect(gain);
            gain.connect(audio.destination);

            oscillator.frequency.value = 880;
            oscillator.type = "sine";

            gain.gain.setValueAtTime(0.25, audio.currentTime);
            gain.gain.exponentialRampToValueAtTime(
                0.001,
                audio.currentTime + 0.35
            );

            oscillator.start();
            oscillator.stop(audio.currentTime + 0.35);

        } catch (error) {
            // Suara bergantung pada izin dan dukungan browser.
        }
    }

    function updateCounter(count) {
        strikeCount = count;

        counterEl.textContent =
            "Pelanggaran: " + strikeCount + " dari 3";

        if (strikeCount >= 3) {
            examActive = false;
            statusEl.innerHTML =
                '<span class="warning">UJIAN DIHENTIKAN.</span>';
        }
    }

    function requestFullscreen() {
        const parentDocument = window.parent.document;
        const target = parentDocument.documentElement;

        if (!parentDocument.fullscreenElement &&
            target.requestFullscreen) {
            target.requestFullscreen().catch(function () {
                statusEl.textContent =
                    "Mode layar penuh tidak berhasil diaktifkan.";
            });
        }
    }

    fullscreenButton.addEventListener("click", function () {
        requestFullscreen();
    });

    // Menerima pengaturan terbaru dari Streamlit
    window.addEventListener("message", function (event) {
        const data = event.data;

        if (!data || data.type !== "streamlit:render") {
            return;
        }

        const args = data.args || {};

        examActive = args.active === true;

        updateCounter(
            Number(args.violation_count || 0)
        );

        const processed = args.last_processed_event_id || null;

        if (processed && processed === lastEventId) {
            pendingEvent = false;
            lastProcessedEventId = processed;
        }

        if (!examActive) {
            statusEl.textContent = "Pemantauan ujian tidak aktif.";
        } else if (strikeCount < 3) {
            statusEl.textContent =
                "Pemantauan aktif. Jangan meninggalkan halaman ujian.";
        }

        if (args.disabled === true) {
            examActive = false;
        }
    });

    // Komponen siap menerima data dari Streamlit
    window.parent.postMessage({
        isStreamlitMessage: true,
        type: "streamlit:componentReady",
        apiVersion: 1
    }, "*");

    // Mengatur tinggi komponen
    window.parent.postMessage({
        isStreamlitMessage: true,
        type: "streamlit:setFrameHeight",
        height: 105
    }, "*");

    // Pantau ketika tab browser menjadi tidak terlihat
    document.addEventListener("visibilitychange", function () {
        if (document.visibilityState === "hidden") {
            sendToStreamlit(
                "TAB_TIDAK_TERLIHAT",
                "Halaman ujian tidak terlihat."
            );
        }
    });

    // Pantau ketika halaman ditinggalkan atau ditutup
    window.addEventListener("pagehide", function () {
        sendToStreamlit(
            "HALAMAN_DITINGGALKAN",
            "Halaman ujian ditinggalkan."
        );
    });

    // Pantau ketika mode layar penuh dihentikan
    try {
        window.parent.document.addEventListener(
            "fullscreenchange",
            function () {
                if (
                    examActive &&
                    !window.parent.document.fullscreenElement
                ) {
                    sendToStreamlit(
                        "KELUAR_LAYAR_PENUH",
                        "Mode layar penuh dihentikan."
                    );
                }
            }
        );
    } catch (error) {
        // Jika akses dokumen induk dibatasi browser,
        // pemantauan fullscreen tidak tersedia.
    }

})();
</script>

</body>
</html>