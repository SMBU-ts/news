// 滚动揭示动效：进入视口时为 .reveal 元素添加 .in
(function () {
  "use strict";
  var els = document.querySelectorAll(".reveal");
  if (!els.length) return;
  if (!("IntersectionObserver" in window)) {
    els.forEach(function (el) { el.classList.add("in"); });
    return;
  }
  var io = new IntersectionObserver(function (entries) {
    entries.forEach(function (e) {
      if (e.isIntersecting) {
        e.target.classList.add("in");
        io.unobserve(e.target);
      }
    });
  }, { threshold: 0.08, rootMargin: "0px 0px -40px 0px" });
  els.forEach(function (el, i) {
    // 轻微错峰，卡片依次浮现
    el.style.transitionDelay = Math.min(i * 40, 320) + "ms";
    io.observe(el);
  });
})();
