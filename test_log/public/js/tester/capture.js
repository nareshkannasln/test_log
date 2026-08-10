// Copyright (c) 2026, Aerele and contributors
// For license information, please see license.txt

/**
 * The capture tools: screen grab, screen recording, clipboard paste and plain files.
 *
 * All of it is native browser API — no libraries to fetch — so the toolbar works the
 * same on a laptop running the site offline as it does against a hosted instance.
 * Screen capture needs a secure context (HTTPS, or localhost), which `supported()`
 * reports so the panel can explain itself instead of failing silently.
 */
(function () {
	const NS = (window.test_log = window.test_log || {});
	if (NS.capture) return;

	const { uuid, t } = NS.util;

	const VIDEO_TYPES = [
		"video/webm;codecs=vp9,opus",
		"video/webm;codecs=vp8,opus",
		"video/webm",
		"video/mp4",
	];

	const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

	function stamp() {
		const now = new Date();
		const pad = (n) => String(n).padStart(2, "0");
		return (
			`${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}` +
			`-${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`
		);
	}

	function kindOf(mime, name = "") {
		if (mime?.startsWith("image/")) return "image";
		if (mime?.startsWith("video/")) return "video";
		if (/\.(png|jpe?g|gif|webp|avif|bmp)$/i.test(name)) return "image";
		if (/\.(mp4|webm|mov|m4v|ogv)$/i.test(name)) return "video";
		return "file";
	}

	/** Wrap a blob in the shape the composer and the offline queue both speak. */
	function makeItem(blob, { file_name, caption = "" } = {}) {
		const name = file_name || `capture-${stamp()}`;
		return {
			id: uuid(),
			file_name: name,
			mime: blob.type || "application/octet-stream",
			size: blob.size,
			kind: kindOf(blob.type, name),
			caption,
			blob,
			file_url: null,
		};
	}

	/**
	 * Why screen capture cannot run here, or null when it can.
	 *
	 * Browsers only hand out the screen on a trusted origin, and `navigator.mediaDevices`
	 * does not even exist elsewhere — so a site opened as http://192.168.1.5:8000 or
	 * http://mysite.local:8000 gets nothing. HTTPS, or plain localhost, is the fix.
	 */
	function unavailableReason() {
		if (!window.isSecureContext) {
			return t(
				"Your browser only allows screen capture on a secure page — open the site over HTTPS, or as localhost."
			);
		}

		if (!navigator.mediaDevices?.getDisplayMedia) {
			return t("This browser does not offer screen capture.");
		}

		return null;
	}

	function supported() {
		return !unavailableReason();
	}

	function recordingUnavailableReason() {
		return unavailableReason() || (window.MediaRecorder ? null : t("This browser cannot record video."));
	}

	function recordingSupported() {
		return !recordingUnavailableReason();
	}

	// ---------------------------------------------------------------- screen grab

	async function grabDisplayStream(options = {}) {
		const blocked = unavailableReason();
		if (blocked) throw new Error(blocked);

		return navigator.mediaDevices.getDisplayMedia({
			video: { frameRate: options.frameRate || 30 },
			audio: options.audio || false,
			preferCurrentTab: options.preferCurrentTab !== false,
		});
	}

	// Chrome hands out a tiny placeholder frame while the capture is starting up; anything
	// this small means no real frame has arrived yet.
	const PLACEHOLDER_SIZE = 2;

	function frameSize(video, track) {
		const settings = track?.getSettings() || {};
		return [
			Math.max(video.videoWidth || 0, settings.width || 0),
			Math.max(video.videoHeight || 0, settings.height || 0),
		];
	}

	function waitForMetadata(video, timeout = 8000) {
		return new Promise((resolve, reject) => {
			if (video.readyState >= 1) {
				resolve();
				return;
			}

			const timer = setTimeout(
				() => reject(new Error(t("The screen capture did not start."))),
				timeout
			);

			video.addEventListener(
				"loadedmetadata",
				() => {
					clearTimeout(timer);
					resolve();
				},
				{ once: true }
			);
		});
	}

	/** Wait for a frame with real dimensions — the metadata alone lies about the size. */
	async function waitForRealFrame(video, track, timeout = 5000) {
		const deadline = Date.now() + timeout;

		while (Date.now() < deadline) {
			const [width, height] = frameSize(video, track);
			if (width > PLACEHOLDER_SIZE && height > PLACEHOLDER_SIZE && video.readyState >= 2) return;

			await nextFrame(video);
		}
	}

	function nextFrame(video) {
		return new Promise((resolve) => {
			const done = () => resolve();
			// A static screen may never present a second frame, so always race a timer.
			const timer = setTimeout(done, 120);

			const settle = () => {
				clearTimeout(timer);
				done();
			};

			if (video.requestVideoFrameCallback) video.requestVideoFrameCallback(settle);
			else requestAnimationFrame(() => requestAnimationFrame(settle));
		});
	}

	/** One frame of whatever the tester picks, as a PNG blob. */
	async function screenshot() {
		const stream = await grabDisplayStream({ preferCurrentTab: true });

		try {
			const track = stream.getVideoTracks()[0];
			const video = document.createElement("video");
			video.srcObject = stream;
			video.muted = true;
			video.playsInline = true;

			await waitForMetadata(video);
			await video.play();
			await waitForRealFrame(video, track);

			const [width, height] = frameSize(video, track);
			if (width <= PLACEHOLDER_SIZE || height <= PLACEHOLDER_SIZE) {
				throw new Error(t("The captured screen came back empty. Try picking a window instead."));
			}

			const canvas = document.createElement("canvas");
			canvas.width = width;
			canvas.height = height;
			canvas.getContext("2d").drawImage(video, 0, 0, width, height);
			video.pause();
			video.srcObject = null;

			const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/png"));
			if (!blob) throw new Error(t("The screenshot could not be encoded."));

			return makeItem(blob, { file_name: `screenshot-${stamp()}.png` });
		} finally {
			stream.getTracks().forEach((track) => track.stop());
		}
	}

	// ---------------------------------------------------------------- screen recording

	function pickVideoType() {
		return VIDEO_TYPES.find((type) => window.MediaRecorder?.isTypeSupported(type)) || "";
	}

	async function mixMicrophone(displayStream) {
		const mic = await navigator.mediaDevices.getUserMedia({ audio: true });
		const context = new (window.AudioContext || window.webkitAudioContext)();
		const destination = context.createMediaStreamDestination();

		[displayStream, mic].forEach((stream) => {
			if (stream.getAudioTracks().length) {
				context.createMediaStreamSource(stream).connect(destination);
			}
		});

		return {
			stream: new MediaStream([
				...displayStream.getVideoTracks(),
				...destination.stream.getAudioTracks(),
			]),
			cleanup() {
				mic.getTracks().forEach((track) => track.stop());
				context.close().catch(() => {});
			},
		};
	}

	/**
	 * Start recording. Resolves with a handle once the tester has picked a surface;
	 * `onStop` fires with the finished item, or with null if it was cancelled.
	 */
	async function record({ withMic = false, limitSeconds = 0, maxBytes = 0, onTick, onStop } = {}) {
		const blocked = recordingUnavailableReason();
		if (blocked) throw new Error(blocked);

		const displayStream = await grabDisplayStream({ audio: true, preferCurrentTab: false });

		let stream = displayStream;
		let cleanupMic = () => {};

		if (withMic) {
			try {
				const mixed = await mixMicrophone(displayStream);
				stream = mixed.stream;
				cleanupMic = mixed.cleanup;
			} catch (error) {
				// No microphone permission — carry on with whatever audio the share gave us.
				console.warn("[test log] microphone unavailable:", error.message);
			}
		}

		const mimeType = pickVideoType();
		const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
		const chunks = [];
		const startedAt = Date.now();

		let cancelled = false;
		let stopped = false;
		let bytes = 0;
		let overflowed = false;

		const ticker = setInterval(() => {
			onTick?.(Math.floor((Date.now() - startedAt) / 1000), bytes);
		}, 500);

		const finish = () => {
			if (stopped) return;
			stopped = true;

			clearInterval(ticker);
			displayStream.getTracks().forEach((track) => track.stop());
			stream.getTracks().forEach((track) => track.stop());
			cleanupMic();

			if (cancelled) {
				onStop?.(null, { cancelled: true });
				return;
			}

			const type = recorder.mimeType || mimeType || "video/webm";
			const extension = type.includes("mp4") ? "mp4" : "webm";
			const blob = new Blob(chunks, { type: type.split(";")[0] });

			// A share that ends before any frame arrives leaves an empty blob. Attaching it
			// would upload nothing and jam the entry, so report it as a failed recording.
			if (!blob.size) {
				onStop?.(null, { empty: true });
				return;
			}

			onStop?.(makeItem(blob, { file_name: `recording-${stamp()}.${extension}` }), {
				seconds: Math.floor((Date.now() - startedAt) / 1000),
				overflowed,
			});
		};

		recorder.ondataavailable = (event) => {
			if (!event.data?.size) return;

			chunks.push(event.data);
			bytes += event.data.size;

			if (maxBytes && bytes > maxBytes && recorder.state === "recording") {
				overflowed = true;
				recorder.stop();
			}
		};

		recorder.onstop = finish;
		recorder.onerror = finish;

		// The browser's own "Stop sharing" bar ends the track without touching us.
		displayStream.getVideoTracks()[0]?.addEventListener("ended", () => {
			if (recorder.state === "recording") recorder.stop();
		});

		recorder.start(1000);

		const limitTimer = limitSeconds
			? setTimeout(() => {
					if (recorder.state === "recording") recorder.stop();
			  }, limitSeconds * 1000)
			: null;

		const shutdown = (isCancel) => {
			cancelled = isCancel;
			clearTimeout(limitTimer);
			if (recorder.state === "recording") recorder.stop();
			else finish();
		};

		return {
			stop: () => shutdown(false),
			cancel: () => shutdown(true),
			get state() {
				return recorder.state;
			},
		};
	}

	// ---------------------------------------------------------------- clipboard & files

	/** Images pasted straight from the OS snipping tool land here. */
	function fromClipboard(event) {
		const items = [...(event.clipboardData?.items || [])];
		const files = items
			.filter((item) => item.kind === "file")
			.map((item) => item.getAsFile())
			.filter(Boolean);

		return files.map((file) =>
			makeItem(file, {
				file_name: file.name && file.name !== "image.png" ? file.name : `pasted-${stamp()}.png`,
			})
		);
	}

	function fromFiles(fileList) {
		return [...fileList].map((file) => makeItem(file, { file_name: file.name }));
	}

	NS.capture = {
		supported,
		recordingSupported,
		unavailableReason,
		recordingUnavailableReason,
		screenshot,
		record,
		fromClipboard,
		fromFiles,
		makeItem,
		sleep,
		stamp,
	};
})();
