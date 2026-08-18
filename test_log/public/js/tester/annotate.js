// Copyright (c) 2026, Aerele and contributors
// For license information, please see license.txt

/**
 * The snipping tool: crop a capture down to the part that matters, ring the broken
 * bit in red, and pixelate anything that should not leave the machine.
 *
 * Opens over the page as its own layer, hands back a fresh image blob, and never
 * touches the network — so it behaves identically offline.
 */
(function () {
	const NS = (window.test_log = window.test_log || {});
	if (NS.annotate) return;

	const { el, t } = NS.util;

	const COLORS = ["#e03131", "#f59f00", "#2f9e44", "#1971c2", "#101113"];

	const TOOLS = [
		{ name: "crop", label: "Crop" },
		{ name: "box", label: "Box" },
		{ name: "arrow", label: "Arrow" },
		{ name: "pen", label: "Pen" },
		{ name: "highlight", label: "Highlight" },
		{ name: "pixelate", label: "Hide" },
	];

	function loadImage(blob) {
		return new Promise((resolve, reject) => {
			const url = URL.createObjectURL(blob);
			const image = new Image();
			image.onload = () => {
				URL.revokeObjectURL(url);
				resolve(image);
			};
			image.onerror = () => {
				URL.revokeObjectURL(url);
				reject(new Error("Could not read the image"));
			};
			image.src = url;
		});
	}

	function canvasFrom(source, width, height, sx = 0, sy = 0, sw = null, sh = null) {
		const canvas = document.createElement("canvas");
		canvas.width = Math.max(1, Math.round(width));
		canvas.height = Math.max(1, Math.round(height));
		canvas
			.getContext("2d")
			.drawImage(
				source,
				sx,
				sy,
				sw ?? source.width,
				sh ?? source.height,
				0,
				0,
				canvas.width,
				canvas.height
			);
		return canvas;
	}

	/**
	 * @param {object} item  capture item holding an image blob
	 * @param {object} options  { startWith: 'crop' | 'box' }
	 * @returns {Promise<object|null>} a new item, or null if the tester backed out
	 */
	async function open(item, { startWith = "box" } = {}) {
		const image = await loadImage(item.blob);

		return new Promise((resolve) => {
			let base = canvasFrom(image, image.naturalWidth, image.naturalHeight);
			const bakedHistory = [];
			let shapes = [];

			let tool = startWith;
			let color = COLORS[0];
			let draft = null;

			// ---------------------------------------------------------- layer

			const canvas = el("canvas", { class: "tl-annotate-canvas" });
			const context = canvas.getContext("2d");
			const hint = el("div", { class: "tl-annotate-hint" });

			const toolButtons = new Map();
			const toolbar = el("div", { class: "tl-annotate-bar" });
			const stage = el("div", { class: "tl-annotate-stage" }, canvas);
			const overlay = el("div", { class: "tl-annotate" }, [toolbar, stage, hint]);

			// ---------------------------------------------------------- drawing

			function strokeWidth() {
				return Math.max(2, Math.round(base.width / 400));
			}

			function drawShape(ctx, shape) {
				ctx.save();
				ctx.strokeStyle = shape.color;
				ctx.fillStyle = shape.color;
				ctx.lineWidth = shape.width;
				ctx.lineCap = "round";
				ctx.lineJoin = "round";

				if (shape.type === "box") {
					ctx.strokeRect(shape.x, shape.y, shape.w, shape.h);
				} else if (shape.type === "highlight") {
					ctx.globalAlpha = 0.3;
					ctx.fillRect(shape.x, shape.y, shape.w, shape.h);
				} else if (shape.type === "pen") {
					ctx.beginPath();
					shape.points.forEach((point, index) =>
						index ? ctx.lineTo(point[0], point[1]) : ctx.moveTo(point[0], point[1])
					);
					ctx.stroke();
				} else if (shape.type === "arrow") {
					const head = Math.max(10, shape.width * 4);
					const angle = Math.atan2(shape.y2 - shape.y1, shape.x2 - shape.x1);
					ctx.beginPath();
					ctx.moveTo(shape.x1, shape.y1);
					ctx.lineTo(shape.x2, shape.y2);
					ctx.stroke();
					ctx.beginPath();
					ctx.moveTo(shape.x2, shape.y2);
					ctx.lineTo(
						shape.x2 - head * Math.cos(angle - Math.PI / 7),
						shape.y2 - head * Math.sin(angle - Math.PI / 7)
					);
					ctx.lineTo(
						shape.x2 - head * Math.cos(angle + Math.PI / 7),
						shape.y2 - head * Math.sin(angle + Math.PI / 7)
					);
					ctx.closePath();
					ctx.fill();
				} else if (shape.type === "pixelate") {
					pixelate(ctx, shape);
				} else if (shape.type === "crop") {
					ctx.save();
					ctx.fillStyle = "rgba(0,0,0,0.45)";
					ctx.beginPath();
					ctx.rect(0, 0, base.width, base.height);
					ctx.rect(shape.x, shape.y, shape.w, shape.h);
					ctx.fill("evenodd");
					ctx.restore();
					ctx.strokeStyle = "#fff";
					ctx.setLineDash([8, 6]);
					ctx.strokeRect(shape.x, shape.y, shape.w, shape.h);
				}

				ctx.restore();
			}

			function pixelate(ctx, shape) {
				const { x, y, w, h } = normalise(shape);
				if (w < 2 || h < 2) return;

				const blocks = Math.max(1, Math.round(Math.max(w, h) / 14));
				const small = canvasFrom(base, blocks, Math.max(1, (blocks * h) / w), x, y, w, h);

				ctx.imageSmoothingEnabled = false;
				ctx.drawImage(small, x, y, w, h);
				ctx.imageSmoothingEnabled = true;
			}

			function normalise(shape) {
				return {
					x: Math.min(shape.x, shape.x + shape.w),
					y: Math.min(shape.y, shape.y + shape.h),
					w: Math.abs(shape.w),
					h: Math.abs(shape.h),
				};
			}

			function render() {
				canvas.width = base.width;
				canvas.height = base.height;
				context.drawImage(base, 0, 0);

				shapes.forEach((shape) => drawShape(context, shape));
				if (draft) drawShape(context, draft);

				fit();
			}

			function fit() {
				const maxWidth = window.innerWidth - 48;
				const maxHeight = window.innerHeight - 150;
				const scale = Math.min(1, maxWidth / base.width, maxHeight / base.height);
				canvas.style.width = `${Math.round(base.width * scale)}px`;
				canvas.style.height = `${Math.round(base.height * scale)}px`;
			}

			function pointAt(event) {
				const rect = canvas.getBoundingClientRect();
				return [
					((event.clientX - rect.left) / rect.width) * base.width,
					((event.clientY - rect.top) / rect.height) * base.height,
				];
			}

			// ---------------------------------------------------------- input

			canvas.addEventListener("pointerdown", (event) => {
				const [x, y] = pointAt(event);
				canvas.setPointerCapture(event.pointerId);

				draft =
					tool === "pen"
						? { type: "pen", points: [[x, y]], color, width: strokeWidth() }
						: tool === "arrow"
						? {
								type: "arrow",
								x1: x,
								y1: y,
								x2: x,
								y2: y,
								color,
								width: strokeWidth(),
						  }
						: {
								type: tool === "crop" ? "crop" : tool,
								x,
								y,
								w: 0,
								h: 0,
								color,
								width: strokeWidth(),
						  };

				render();
			});

			canvas.addEventListener("pointermove", (event) => {
				if (!draft) return;

				const [x, y] = pointAt(event);
				if (draft.type === "pen") draft.points.push([x, y]);
				else if (draft.type === "arrow") Object.assign(draft, { x2: x, y2: y });
				else Object.assign(draft, { w: x - draft.x, h: y - draft.y });

				render();
			});

			canvas.addEventListener("pointerup", () => {
				if (!draft) return;

				const shape = draft;
				draft = null;

				if (shape.type === "crop") {
					applyCrop(shape);
				} else if (shape.type === "pen" ? shape.points.length > 1 : hasSize(shape)) {
					shapes.push(
						shape.type === "pixelate"
							? { ...normalise(shape), type: "pixelate" }
							: shape
					);
				}

				render();
			});

			function hasSize(shape) {
				if (shape.type === "arrow")
					return Math.hypot(shape.x2 - shape.x1, shape.y2 - shape.y1) > 8;
				return Math.abs(shape.w) > 6 && Math.abs(shape.h) > 6;
			}

			function applyCrop(shape) {
				const box = normalise(shape);
				if (box.w < 12 || box.h < 12) return;

				// Bake what is on screen, then crop it — annotations keep their place.
				const baked = canvasFrom(canvas, canvas.width, canvas.height);
				bakedHistory.push(base);
				base = canvasFrom(baked, box.w, box.h, box.x, box.y, box.w, box.h);
				shapes = [];
				setTool("box");
			}

			function undo() {
				if (shapes.length) shapes.pop();
				else if (bakedHistory.length) base = bakedHistory.pop();
				render();
			}

			// ---------------------------------------------------------- toolbar

			function setTool(name) {
				tool = name;
				toolButtons.forEach((button, key) =>
					button.classList.toggle("is-active", key === name)
				);
				hint.textContent =
					name === "crop"
						? t("Drag over the part you want to keep.")
						: name === "pixelate"
						? t("Drag over anything that should be hidden.")
						: t("Drag on the image to mark it up.");
			}

			TOOLS.forEach((entry) => {
				const button = el(
					"button",
					{
						type: "button",
						class: "tl-btn tl-btn-tool",
						title: t(entry.label),
						onclick: () => setTool(entry.name),
					},
					t(entry.label)
				);
				toolButtons.set(entry.name, button);
				toolbar.append(button);
			});

			toolbar.append(el("span", { class: "tl-annotate-sep" }));

			COLORS.forEach((swatch) => {
				const button = el("button", {
					type: "button",
					class: "tl-swatch",
					style: { background: swatch },
					title: swatch,
					onclick: () => {
						color = swatch;
						toolbar
							.querySelectorAll(".tl-swatch")
							.forEach((node) =>
								node.classList.toggle("is-active", node.title === swatch)
							);
					},
				});
				if (swatch === color) button.classList.add("is-active");
				toolbar.append(button);
			});

			toolbar.append(
				el("span", { class: "tl-annotate-sep" }),
				el("button", { type: "button", class: "tl-btn", onclick: undo }, t("Undo")),
				el("span", { class: "tl-annotate-spacer" }),
				el(
					"button",
					{ type: "button", class: "tl-btn", onclick: () => close(null) },
					t("Cancel")
				),
				el(
					"button",
					{ type: "button", class: "tl-btn tl-btn-primary", onclick: () => finish() },
					t("Attach")
				)
			);

			// ---------------------------------------------------------- lifecycle

			function close(result) {
				window.removeEventListener("keydown", onKey);
				window.removeEventListener("resize", fit);
				overlay.remove();
				resolve(result);
			}

			function onKey(event) {
				if (event.key === "Escape") {
					event.stopPropagation();
					close(null);
				} else if ((event.ctrlKey || event.metaKey) && event.key === "z") {
					event.preventDefault();
					undo();
				}
			}

			function finish() {
				draft = null;
				render();
				canvas.toBlob((blob) => {
					close({
						...item,
						blob,
						size: blob.size,
						mime: "image/png",
						kind: "image",
						file_name: item.file_name.replace(/\.[^.]+$/, "") + ".png",
						file_url: null,
					});
				}, "image/png");
			}

			window.addEventListener("keydown", onKey);
			window.addEventListener("resize", fit);
			document.body.append(overlay);

			setTool(startWith);
			render();
		});
	}

	NS.annotate = { open, COLORS };
})();
