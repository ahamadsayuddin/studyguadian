(function () {
  const root = document.documentElement;
  const dashboardShell = document.querySelector('.dashboard-shell');
  if (!dashboardShell) return;

  const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value;
  const themeToggle = document.getElementById('themeToggle');
  
  // --- Animation: Magnetic Effect ---
  const magneticButtons = document.querySelectorAll('.primary-button, .secondary-button, .brand-mark');
  magneticButtons.forEach(btn => {
    btn.addEventListener('mousemove', (e) => {
      const rect = btn.getBoundingClientRect();
      const x = e.clientX - rect.left - rect.width / 2;
      const y = e.clientY - rect.top - rect.height / 2;
      btn.style.transform = `translate(${x * 0.2}px, ${y * 0.2}px)`;
    });
    btn.addEventListener('mouseleave', () => {
      btn.style.transform = '';
    });
  });

  // --- Animation: Staggered Reveal ---
  const observerOptions = { threshold: 0.1, rootMargin: '0px 0px -50px 0px' };
  const revealObserver = new IntersectionObserver((entries) => {
    entries.forEach((entry, i) => {
      if (entry.isIntersecting) {
        setTimeout(() => {
          entry.target.classList.add('is-visible');
        }, i * 100);
      }
    });
  }, observerOptions);

  document.querySelectorAll('.glass-card, .stat-card, section > div').forEach(el => {
    el.classList.add('reveal-hidden');
    revealObserver.observe(el);
  });

  // --- Common Logic (Theme) ---
  themeToggle?.addEventListener('click', async () => {
    const nextTheme = root.dataset.theme === 'dark' ? 'light' : 'dark';
    root.dataset.theme = nextTheme;
    fetch('/theme/update/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
      body: JSON.stringify({ theme: nextTheme }),
    });
  });

  // ... (rest of the logic preserved below)

  // --- Document Lab (Study Lab Page) ---
  const documentSection = document.getElementById('document-lab');

  if (documentSection) {
    const uploadUrl = documentSection?.dataset.uploadUrl;
    const mcqUrl = documentSection?.dataset.mcqUrl;
    const documentUploadForm = document.getElementById('documentUploadForm');
    const documentInput = document.getElementById('documentInput');
    const documentExplanationBox = document.getElementById('documentExplanationBox');
    const explanationText = document.getElementById('explanationText');
    const mcqGeneratorPanel = document.getElementById('mcqGeneratorPanel');

    documentUploadForm?.addEventListener('submit', async (e) => {
      e.preventDefault();
      const file = documentInput.files[0];
      if (!file) return;

      const formData = new FormData();
      formData.append('document', file);
      const btn = document.getElementById('uploadDocumentButton');
      btn.disabled = true; btn.textContent = "Analyzing...";

      try {
        const resp = await fetch(uploadUrl, {
          method: 'POST', headers: { 'X-CSRFToken': csrfToken }, body: formData
        });
        const data = await resp.json();
        if (data.status === 'ok') {
          explanationText.textContent = data.explanation;
          documentExplanationBox.style.display = 'block';
          mcqGeneratorPanel.style.display = 'block';
          // Store doc ID globally for this session or redirect to Assessment?
          window.__currentDocumentId = data.document_id;
        } else alert(data.error || "Upload failed");
      } catch (err) { alert("Error: " + err); }
      finally { btn.disabled = false; btn.textContent = "Upload & Explain"; }
    });

    const generateMcqButton = document.getElementById('generateMcqButton');
    generateMcqButton?.addEventListener('click', async () => {
      const docId = window.__currentDocumentId;
      if (!docId) {
          alert("Mundhu document upload cheyyali.");
          return;
      }
      
      const count = document.getElementById('mcqCountInput')?.value || 10;
      generateMcqButton.disabled = true;
      generateMcqButton.textContent = "Generating...";
      
      try {
          const resp = await fetch(mcqUrl, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
              body: JSON.stringify({ document_id: docId, count: count })
          });
          const data = await resp.json();
          if (data.status === 'ok') {
              // If we have an on-page testStatusBox, just update it instead of redirecting
              const onPageStatusBox = document.getElementById('testStatusBox');
              if (onPageStatusBox) {
                  currentMcqs = data.mcqs;
                  renderTestStatus(currentMcqs);
                  // Scroll to the assessment section
                  document.getElementById('malfunction-lab')?.scrollIntoView({ behavior: 'smooth' });
              } else {
                  window.location.href = "/assessment/";
              }
          } else {
              alert(data.error);
          }
      } catch (err) {
          alert("Error: " + err);
      } finally {
          // Force reset of UI state
          setTimeout(() => {
              generateMcqButton.disabled = false;
              generateMcqButton.textContent = "Generate Test";
          }, 100);
      }
    });

  }

  // --- Secure Testing & Assessments (Shared across Lab/Assessment) ---
  const toggleCameraButton = document.getElementById('toggleCameraButton');
  if (toggleCameraButton) {
    const cameraPreview = document.getElementById('cameraPreview');
    const cameraEmpty = document.getElementById('cameraEmpty');
    const testModal = document.getElementById('testModal');
    const malfunctionStatus = document.getElementById('malfunctionStatus');
    const malfunctionResult = document.getElementById('malfunctionResult');
    const submitTestButton = document.getElementById('submitTestButton');
    const testMalfunctionBadge = document.getElementById('testMalfunctionBadge');
    
    let detector = null;
    let faceDetector = null;
    let cameraStream = null;
    let isTestActive = false;
    let malpracticeDetected = false;
    let malpracticeReason = '';
    let selectedAnswers = [];
    let focusViolationStartedAt = null;
    let lastFaceCheckAt = 0;
    const focusGracePeriodMs = 10000;
    // Shared state for current test questions
    if (typeof currentMcqs === 'undefined') window.currentMcqs = null;

    function renderTestStatus(mcqs) {
        const statusBox = document.getElementById('testStatusBox');
        if (!mcqs || mcqs.length === 0) return;
        
        statusBox.innerHTML = `
            <div class="glass-card" style="padding: 1.5rem; background: var(--surface-soft); border: 1px solid var(--primary); text-align: center;">
                <h4 style="margin-top:0;">Test is Ready!</h4>
                <p>Total Questions: ${mcqs.length}</p>
                <div class="button-container" style="margin-top:20px;">
                   <button type="button" class="primary-button" id="startAssessmentButton" style="width:100%; height:44px;">Start Secure Test</button>
                   <button type="button" class="ghost-link" onclick="window.location.reload()" style="margin-top:10px; font-size:0.8rem;">Change Document</button>
                </div>
            </div>
        `;
        
        document.getElementById('startAssessmentButton')?.addEventListener('click', async () => {
            if (!cameraStream) {
              await startCamera();
            }
            if (cameraStream) startTest(mcqs);
        });
    }

    function startTest(mcqs) {
        if (!mcqs) return;
        isTestActive = true;
        malpracticeDetected = false;
        malpracticeReason = '';
        selectedAnswers = new Array(mcqs.length).fill(null);
        focusViolationStartedAt = null;
        const container = document.getElementById('testQuestionsContainer');
        container.innerHTML = '';
        if (testMalfunctionBadge) {
            testMalfunctionBadge.textContent = 'Secure';
            testMalfunctionBadge.style.background = 'var(--brand-mint)';
            testMalfunctionBadge.style.color = '#000';
        }
        
        mcqs.forEach((q, idx) => {
            const qDiv = document.createElement('div');
            qDiv.className = 'test-question';
            qDiv.style.marginBottom = '20px';
            qDiv.innerHTML = `
                <p><strong>Q${idx+1}: ${q.question}</strong></p>
                <div class="options-grid" style="display:grid; grid-template-columns: 1fr 1fr; gap:10px; margin-top:10px;">
                    ${q.options.map(opt => `
                        <button type="button" class="secondary-button option-btn" style="text-align:left;" data-answer="${q.answer}" data-question-index="${idx}" data-option="${String(opt).replace(/"/g, '&quot;')}">${opt}</button>
                    `).join('')}
                </div>
            `;
            container.appendChild(qDiv);
        });
        
        testModal.style.display = 'block';
        startTestTimer();
    }

    function selectOption(btn) {
        const parent = btn.parentElement;
        parent.querySelectorAll('.option-btn').forEach(b => b.classList.remove('active', 'correct', 'wrong'));
        btn.classList.add('active');
        const questionIndex = Number(btn.dataset.questionIndex);
        selectedAnswers[questionIndex] = btn.dataset.option || btn.textContent.trim();
    }

    document.getElementById('testQuestionsContainer')?.addEventListener('click', (e) => {
        const btn = e.target.closest('.option-btn');
        if (!btn) return;
        selectOption(btn);
    });

    function startTestTimer() {
        let seconds = 25 * 60;
        const timerLabel = document.getElementById('testTimerLabel');
        const interval = setInterval(() => {
            if (!isTestActive) { clearInterval(interval); return; }
            seconds--;
            const mins = Math.floor(seconds / 60); const secs = seconds % 60;
            timerLabel.textContent = `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
            if (seconds <= 0) { clearInterval(interval); submitTest(); }
        }, 1000);
    }

    async function submitTest(autoSubmitted = false) {
        if (!isTestActive || !Array.isArray(currentMcqs) || currentMcqs.length === 0) return;

        isTestActive = false;
        const submitUrl = testModal?.dataset.submitUrl;
        const answeredCount = selectedAnswers.filter(Boolean).length;
        const correct = currentMcqs.reduce((score, q, idx) => {
            return score + (selectedAnswers[idx] && selectedAnswers[idx] === q.answer ? 1 : 0);
        }, 0);
        const total = currentMcqs.length;
        const timeText = document.getElementById('testTimerLabel')?.textContent || '25:00';
        const [mins, secs] = timeText.split(':').map(Number);
        const remainingSeconds = ((Number.isFinite(mins) ? mins : 0) * 60) + (Number.isFinite(secs) ? secs : 0);
        const timeTaken = (25 * 60) - remainingSeconds;

        try {
            if (submitUrl) {
                await fetch(submitUrl, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
                    body: JSON.stringify({
                        total,
                        correct,
                        time_taken: Math.max(timeTaken, 0),
                        malpractice: malpracticeDetected,
                        reason: malpracticeReason,
                    })
                });
            }
        } catch (err) {
            console.error('Submit failed', err);
        }

        testModal.style.display = 'none';
        const statusBox = document.getElementById('testStatusBox');
        if (statusBox) {
            statusBox.innerHTML = `
                <div class="glass-card" style="padding: 1.5rem; background: var(--surface-soft); border: 1px solid var(--primary);">
                    <h4 style="margin-top:0;">Test Submitted</h4>
                    <p>Score: ${correct}/${total}</p>
                    <p>Answered: ${answeredCount}/${total}</p>
                    <p>${autoSubmitted ? `Auto-submitted due to malpractice: ${malpracticeReason || 'rule violation'}.` : 'Your answers were submitted successfully.'}</p>
                </div>
            `;
        }
    }

    // Check for pending test data on load
    const pendingDataEl = document.getElementById('pending-test-data');
    if (pendingDataEl) {
        try {
            const data = JSON.parse(pendingDataEl.textContent);
            if (data && data.length > 0) {
                currentMcqs = data;
                renderTestStatus(currentMcqs);
            }
        } catch (e) { console.error("Pending data error", e); }
    }

    // Integrated Generation logic
    const assessmentGenBtn = document.getElementById('assessmentGenerateButton');
    if (assessmentGenBtn) {
        assessmentGenBtn.addEventListener('click', async () => {
            const docId = document.getElementById('assessmentDocSelect').value;
            const count = document.getElementById('assessmentMcqCount').value;
            const mcqUrl = document.getElementById('testStatusBox').dataset.mcqUrl;
            assessmentGenBtn.disabled = true;
            assessmentGenBtn.textContent = "Generating AI Test...";

            try {
                const resp = await fetch(mcqUrl, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
                    body: JSON.stringify({ document_id: docId, count: count })
                });
                const data = await resp.json();
                if (data.status === 'ok') {
                    currentMcqs = data.mcqs;
                    renderTestStatus(currentMcqs);
                } else alert(data.error);
            } catch (err) { alert("Error: " + err); }
            finally {
                assessmentGenBtn.disabled = false;
                assessmentGenBtn.textContent = "Generate Assessment";
            }
        });
    }

    loadDetectionModel();
    loadFaceDetectionModel();

    async function loadDetectionModel() {
        if (typeof cocoSsd === 'undefined') return;
        try {
            detector = await cocoSsd.load();
            console.log("Model loaded.");
        } catch (e) { console.error("Model fail", e); }
    }

    async function loadFaceDetectionModel() {
        if (typeof blazeface === 'undefined') return;
        try {
            faceDetector = await blazeface.load();
            console.log("Face model loaded.");
        } catch (e) { console.error("Face model fail", e); }
    }

    toggleCameraButton.addEventListener('click', async () => {
        if (cameraStream) stopCamera(); else startCamera();
    });

    async function startCamera() {
        try {
            cameraStream = await navigator.mediaDevices.getUserMedia({ video: true });
            cameraPreview.srcObject = cameraStream;
            cameraEmpty.style.display = 'none'; cameraPreview.style.display = 'block';
            toggleCameraButton.textContent = "Disable Camera";
            malfunctionResult.style.display = 'flex';
            malfunctionStatus.textContent = "Monitoring...";
            malfunctionStatus.style.color = "var(--brand-mint)";
            focusViolationStartedAt = null;
            detectCycle();
        } catch (e) { alert("Webcam access required."); }
    }

    function stopCamera() {
        if (cameraStream) {
            cameraStream.getTracks().forEach(t => t.stop());
            cameraStream = null;
        }
        cameraPreview.style.display = 'none'; cameraEmpty.style.display = 'block';
        toggleCameraButton.textContent = "Enable Camera";
        malfunctionResult.style.display = 'none';
        focusViolationStartedAt = null;
    }

    function setViolationState(message, color = 'red') {
        malfunctionStatus.textContent = message;
        malfunctionStatus.style.color = color;
        if (testMalfunctionBadge) {
            testMalfunctionBadge.textContent = message;
            testMalfunctionBadge.style.background = color;
            testMalfunctionBadge.style.color = '#fff';
        }
    }

    function resetSecureState() {
        malfunctionStatus.textContent = "Monitoring...";
        malfunctionStatus.style.color = "var(--brand-mint)";
        if (testMalfunctionBadge && !malpracticeDetected) {
            testMalfunctionBadge.textContent = "Secure";
            testMalfunctionBadge.style.background = "var(--brand-mint)";
            testMalfunctionBadge.style.color = "#000";
        }
    }

    async function evaluateFaceFocus() {
        if (!faceDetector || !cameraPreview.videoWidth || !cameraPreview.videoHeight) {
            return { violation: false, reason: '' };
        }

        const now = performance.now();
        if (now - lastFaceCheckAt < 400) {
            return { violation: false, reason: '' };
        }
        lastFaceCheckAt = now;

        const faces = await faceDetector.estimateFaces(cameraPreview, false);
        const face = faces && faces[0];
        if (!face) {
            return { violation: true, reason: 'No face detected in camera.' };
        }

        const topLeft = face.topLeft || [0, 0];
        const bottomRight = face.bottomRight || [0, 0];
        const faceCenterX = (topLeft[0] + bottomRight[0]) / 2;
        const faceCenterY = (topLeft[1] + bottomRight[1]) / 2;
        const videoCenterX = cameraPreview.videoWidth / 2;
        const videoCenterY = cameraPreview.videoHeight / 2;
        const xOffsetRatio = Math.abs(faceCenterX - videoCenterX) / videoCenterX;
        const yOffsetRatio = Math.abs(faceCenterY - videoCenterY) / videoCenterY;

        if (xOffsetRatio > 0.38 || yOffsetRatio > 0.38) {
            return { violation: true, reason: 'Face not focused on the camera.' };
        }

        return { violation: false, reason: '' };
    }

    async function detectCycle() {
        if (!cameraStream || !cameraStream.active) return;
        try {
            const predictions = detector ? await detector.detect(cameraPreview) : [];
            const phone = predictions.find(p => p.class === 'cell phone');
            if (phone) {
                setViolationState("PHONE DETECTED!");
                if (isTestActive && !malpracticeDetected) {
                    malpracticeDetected = true;
                    malpracticeReason = "Mobile phone detected during test.";
                    submitTest(true);
                    return;
                }
            } else {
                const faceStatus = await evaluateFaceFocus();
                if (faceStatus.violation) {
                    if (!focusViolationStartedAt) {
                        focusViolationStartedAt = Date.now();
                    }
                    const elapsedMs = Date.now() - focusViolationStartedAt;
                    const secondsLeft = Math.max(0, Math.ceil((focusGracePeriodMs - elapsedMs) / 1000));
                    setViolationState(`${faceStatus.reason} Auto-submit in ${secondsLeft}s.`);

                    if (isTestActive && elapsedMs >= focusGracePeriodMs && !malpracticeDetected) {
                        malpracticeDetected = true;
                        malpracticeReason = faceStatus.reason;
                        submitTest(true);
                        return;
                    }
                } else {
                    focusViolationStartedAt = null;
                    resetSecureState();
                }
            }
        } catch (e) {}
        if (cameraStream && cameraStream.active) requestAnimationFrame(detectCycle);
    }

    submitTestButton?.addEventListener('click', () => submitTest());
  }

  // --- Focus Timer & Ambient (Focus Page) ---
  const startTimerButton = document.getElementById('startTimerButton');
  if (startTimerButton) {
    const timerLabel = document.getElementById('timerLabel');
    const timerProgress = document.getElementById('timerProgress');
    const resetTimerButton = document.getElementById('resetTimerButton');
    const presetButtons = document.querySelectorAll('[data-preset]');
    const ambientList = document.getElementById('ambientList');

    let timerRunning = false;
    let timerSeconds = 25 * 60;
    let timerInterval = null;
    let timerPreset = 'flow';

    const presetMap = {
        flow: { study: 25 * 60, break: 5 * 60 },
        deep: { study: 50 * 60, break: 10 * 60 },
    };

    presetButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            presetButtons.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            timerPreset = btn.dataset.preset;
            resetTimer();
        });
    });

    startTimerButton.addEventListener('click', () => {
        if (timerRunning) pauseTimer(); else startTimer();
    });
    resetTimerButton?.addEventListener('click', resetTimer);

    function startTimer() {
        timerRunning = true; startTimerButton.textContent = "Pause Session";
        timerInterval = setInterval(() => {
            timerSeconds--; updateTimerUI();
            if (timerSeconds <= 0) {
                clearInterval(timerInterval);
                alert("Time's up!");
            }
        }, 1000);
    }
    function pauseTimer() {
        timerRunning = false; startTimerButton.textContent = "Start Session";
        clearInterval(timerInterval);
    }
    function resetTimer() {
        pauseTimer();
        timerSeconds = presetMap[timerPreset].study;
        updateTimerUI();
    }
    function updateTimerUI() {
        const mins = Math.floor(timerSeconds / 60); const secs = timerSeconds % 60;
        timerLabel.textContent = `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
        const total = presetMap[timerPreset].study;
        const prog = 1 - (timerSeconds / total);
        if (timerProgress) timerProgress.style.strokeDashoffset = 565.49 - (prog * 565.49);
    }

    // Ambient Logic
    const ambientDataScript = document.getElementById('ambientTrackData');
    if (ambientDataScript && ambientList) {
        const tracks = JSON.parse(ambientDataScript.textContent);
        tracks.forEach(track => {
            const card = document.createElement('div');
            card.className = 'ambient-card-item glass-card';
            card.style.padding = '1rem';
            card.style.cursor = 'pointer';
            card.innerHTML = `<strong>${track.name}</strong><p class="muted">${track.category}</p>`;
            card.onclick = () => {
                alert(`Playing: ${track.name} (Simulated audio)`);
            };
            ambientList.appendChild(card);
        });
    }
  }

  // --- Analytics Charts ---
  const studyChartCanvas = document.getElementById('studyChart');
  if (studyChartCanvas && typeof Chart !== 'undefined') {
      const studyData = JSON.parse(document.getElementById('weeklyStudyData').textContent);
      const moodData = JSON.parse(document.getElementById('moodTrendData').textContent);

      new Chart(studyChartCanvas, {
          type: 'bar',
          data: {
              labels: studyData.labels,
              datasets: [{
                  label: 'Minutes Focused',
                  data: studyData.values,
                  backgroundColor: 'rgba(0, 255, 255, 0.4)',
                  borderColor: 'rgba(0, 255, 255, 1)',
                  borderWidth: 1
              }]
          },
          options: { responsive: true, scales: { y: { beginAtZero: true } } }
      });

      const moodCanvas = document.getElementById('moodChart');
      if (moodCanvas) {
          new Chart(moodCanvas, {
              type: 'line',
              data: {
                  labels: moodData.labels,
                  datasets: [{
                      label: 'Confidence level',
                      data: moodData.values,
                      borderColor: 'rgba(255, 0, 255, 1)',
                      tension: 0.4
                  }]
              },
              options: { responsive: true }
          });
      }

      // Recommendations
      const recsList = document.getElementById('recommendations-list');
      const recDataScript = document.getElementById('recommendationData');
      if (recsList && recDataScript) {
          const recs = JSON.parse(recDataScript.textContent);
          recs.forEach(rec => {
              const div = document.createElement('div');
              div.className = 'glass-card';
              div.style.padding = '1rem';
              div.innerHTML = `<h4 style="color:var(--brand-mint);">${rec.title}</h4><p class="muted">${rec.description}</p>`;
              recsList.appendChild(div);
          });
      }
  }

})();
 stories
