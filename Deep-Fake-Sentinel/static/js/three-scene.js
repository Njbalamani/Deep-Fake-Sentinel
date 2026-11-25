(function () {
  'use strict';

  var mounted = new WeakMap();

  function labelTexture(title, glyph) {
    var canvas = document.createElement('canvas');
    canvas.width = 512;
    canvas.height = 320;
    var ctx = canvas.getContext('2d');
    ctx.fillStyle = '#081224';
    ctx.fillRect(0, 0, 512, 320);
    ctx.strokeStyle = 'rgba(201,210,223,0.10)';
    ctx.lineWidth = 1;
    for (var x = 0; x <= 512; x += 32) {
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, 320);
      ctx.stroke();
    }
    for (var y = 0; y <= 320; y += 32) {
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(512, y);
      ctx.stroke();
    }
    ctx.strokeStyle = '#d4af37';
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.moveTo(18, 66);
    ctx.lineTo(18, 18);
    ctx.lineTo(66, 18);
    ctx.moveTo(446, 18);
    ctx.lineTo(494, 18);
    ctx.lineTo(494, 66);
    ctx.moveTo(494, 254);
    ctx.lineTo(494, 302);
    ctx.lineTo(446, 302);
    ctx.moveTo(66, 302);
    ctx.lineTo(18, 302);
    ctx.lineTo(18, 254);
    ctx.stroke();
    ctx.fillStyle = 'rgba(212,175,55,0.85)';
    ctx.font = '72px monospace';
    ctx.textAlign = 'center';
    ctx.fillText(glyph, 256, 168);
    ctx.fillStyle = '#f3dfa0';
    ctx.font = '22px monospace';
    ctx.fillText(title, 256, 224);
    ctx.fillStyle = 'rgba(201,210,223,0.55)';
    ctx.font = '13px monospace';
    ctx.fillText('DFS / EVIDENCE PLANE', 256, 250);
    var texture = new THREE.CanvasTexture(canvas);
    texture.anisotropy = 2;
    return texture;
  }

  function mount(container, options) {
    if (!container || typeof THREE === 'undefined') return null;
    destroy(container);
    var opts = options || {};
    var width = Math.max(container.clientWidth, 1);
    var height = Math.max(container.clientHeight, 1);
    var renderer;
    try {
      renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true, powerPreference: 'low-power' });
    } catch (error) {
      return null;
    }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
    renderer.setSize(width, height, false);
    renderer.setClearColor(0x000000, 0);
    container.appendChild(renderer.domElement);

    var scene = new THREE.Scene();
    var camera = new THREE.PerspectiveCamera(42, width / height, 0.1, 120);
    camera.position.set(0, 0.2, 10.5);

    scene.add(new THREE.AmbientLight(0xc9d2df, 0.65));
    var key = new THREE.DirectionalLight(0xf3dfa0, 1.1);
    key.position.set(3, 5, 7);
    scene.add(key);
    var rim = new THREE.PointLight(0x4d7ac0, 0.8, 30);
    rim.position.set(-5, -2, 4);
    scene.add(rim);

    var disposables = [];
    var planes = [];
    var specs = [
      { title: 'IMAGE', glyph: '◈', x: -2.75, y: 0.35, z: -1.4, ry: 0.32 },
      { title: 'VIDEO', glyph: '▶', x: 0.05, y: 0.75, z: 0.2, ry: 0 },
      { title: 'AUDIO', glyph: '∿', x: 2.8, y: -0.25, z: -1.2, ry: -0.3 }
    ];

    specs.forEach(function (spec, index) {
      var group = new THREE.Group();
      var texture = labelTexture(spec.title, spec.glyph);
      var geometry = new THREE.PlaneGeometry(2.05, 1.28);
      var material = new THREE.MeshBasicMaterial({ map: texture, transparent: true, opacity: 0.92, side: THREE.DoubleSide });
      var plane = new THREE.Mesh(geometry, material);
      var edgeGeometry = new THREE.EdgesGeometry(geometry);
      var edgeMaterial = new THREE.LineBasicMaterial({ color: 0xd4af37, transparent: true, opacity: 0.55 });
      var edges = new THREE.LineSegments(edgeGeometry, edgeMaterial);
      group.add(plane);
      group.add(edges);
      group.position.set(spec.x, spec.y, spec.z);
      group.rotation.y = spec.ry;
      group.rotation.x = -0.04 + index * 0.03;
      scene.add(group);
      planes.push({ group: group, baseY: spec.y, phase: index * 1.7, speed: 0.55 + index * 0.12 });
      disposables.push(geometry, material, texture, edgeGeometry, edgeMaterial);
    });

    var nodeGeometry = new THREE.SphereGeometry(0.065, 12, 12);
    var nodeMaterial = new THREE.MeshBasicMaterial({ color: 0xf3dfa0 });
    var positions = [
      [-3.8, -1.5, -2], [-1.8, -1.85, -1], [-0.7, 1.9, -2], [1.4, -1.7, -1.6], [3.6, 1.5, -2], [0, -2.1, -2.4]
    ];
    var nodes = positions.map(function (point) {
      var node = new THREE.Mesh(nodeGeometry, nodeMaterial);
      node.position.set(point[0], point[1], point[2]);
      scene.add(node);
      return node;
    });
    disposables.push(nodeGeometry, nodeMaterial);

    var linkPoints = [];
    for (var i = 0; i < nodes.length - 1; i += 1) {
      linkPoints.push(nodes[i].position.clone(), nodes[i + 1].position.clone());
    }
    linkPoints.push(nodes[0].position.clone(), nodes[5].position.clone());
    var linkGeometry = new THREE.BufferGeometry().setFromPoints(linkPoints);
    var linkMaterial = new THREE.LineBasicMaterial({ color: 0x7fb8f0, transparent: true, opacity: 0.22 });
    var links = new THREE.LineSegments(linkGeometry, linkMaterial);
    scene.add(links);
    disposables.push(linkGeometry, linkMaterial);

    var particleCount = opts.particles || 120;
    var particlePositions = new Float32Array(particleCount * 3);
    for (var p = 0; p < particleCount; p += 1) {
      particlePositions[p * 3] = (Math.random() - 0.5) * 13;
      particlePositions[p * 3 + 1] = (Math.random() - 0.5) * 7;
      particlePositions[p * 3 + 2] = -3 - Math.random() * 5;
    }
    var particleGeometry = new THREE.BufferGeometry();
    particleGeometry.setAttribute('position', new THREE.BufferAttribute(particlePositions, 3));
    var particleMaterial = new THREE.PointsMaterial({ color: 0xd4af37, size: 0.045, transparent: true, opacity: 0.65 });
    var particles = new THREE.Points(particleGeometry, particleMaterial);
    scene.add(particles);
    disposables.push(particleGeometry, particleMaterial);

    var reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    var visible = true;
    var frame = 0;
    var clock = new THREE.Clock();

    function render() {
      renderer.render(scene, camera);
    }

    function animate() {
      frame = window.requestAnimationFrame(animate);
      if (!visible || document.hidden) return;
      var time = clock.getElapsedTime();
      planes.forEach(function (item) {
        item.group.position.y = item.baseY + Math.sin(time * item.speed + item.phase) * 0.16;
        item.group.rotation.z = Math.sin(time * 0.24 + item.phase) * 0.035;
      });
      particles.rotation.z = time * 0.012;
      links.material.opacity = 0.18 + Math.sin(time * 0.8) * 0.06;
      render();
    }

    function resize() {
      var nextWidth = Math.max(container.clientWidth, 1);
      var nextHeight = Math.max(container.clientHeight, 1);
      camera.aspect = nextWidth / nextHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(nextWidth, nextHeight, false);
      render();
    }

    var observer = null;
    if (typeof ResizeObserver !== 'undefined') {
      observer = new ResizeObserver(resize);
      observer.observe(container);
    } else {
      window.addEventListener('resize', resize);
    }

    var visibilityObserver = null;
    if (typeof IntersectionObserver !== 'undefined') {
      visibilityObserver = new IntersectionObserver(function (entries) {
        visible = entries[0].isIntersecting;
      }, { threshold: 0.02 });
      visibilityObserver.observe(container);
    }

    var handle = {
      render: render,
      resize: resize,
      destroy: function () {
        window.cancelAnimationFrame(frame);
        if (observer) observer.disconnect();
        else window.removeEventListener('resize', resize);
        if (visibilityObserver) visibilityObserver.disconnect();
        disposables.forEach(function (item) {
          if (item && typeof item.dispose === 'function') item.dispose();
        });
        renderer.dispose();
        if (renderer.domElement && renderer.domElement.parentNode === container) {
          container.removeChild(renderer.domElement);
        }
        if (mounted.get(container) === handle) mounted.delete(container);
      }
    };

    mounted.set(container, handle);
    resize();
    if (!reducedMotion) animate();
    else render();
    return handle;
  }

  function destroy(container) {
    if (!container) return;
    var handle = mounted.get(container);
    if (handle) handle.destroy();
  }

  window.SentinelScene = { mount: mount, destroy: destroy };
})();
