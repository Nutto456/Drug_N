document.addEventListener('DOMContentLoaded', () => {
    const drugInput = document.getElementById('drug-input');
    const suggestionsList = document.getElementById('suggestions-list');
    const selectedDrugsList = document.getElementById('selected-drugs-list');
    const checkBtn = document.getElementById('check-btn');
    const clearBtn = document.getElementById('clear-btn');
    const loadingEl = document.getElementById('loading');
    const resultsEl = document.getElementById('results');
    const statusDot = document.getElementById('status-dot');
    const statusText = document.getElementById('status-text');
    
    const API_BASE_URL = 'http://localhost:8000';
    let selectedDrugs = [];
    let timeoutId;

    const updateCheckButtonState = () => {
        checkBtn.disabled = selectedDrugs.length < 2;
    };

    const addDrug = (drug) => {
        if (!selectedDrugs.some(d => d.name === drug.name)) {
            selectedDrugs.push(drug);
            renderSelectedDrugs();
            updateCheckButtonState();
            drugInput.value = '';
            suggestionsList.innerHTML = '';
        }
    };

    const removeDrug = (drugName) => {
        selectedDrugs = selectedDrugs.filter(d => d.name !== drugName);
        renderSelectedDrugs();
        updateCheckButtonState();
        if (selectedDrugs.length < 2) {
            resultsEl.innerHTML = '';
        }
    };

    const renderSelectedDrugs = () => {
        selectedDrugsList.innerHTML = '';
        selectedDrugs.forEach(drug => {
            const drugTag = document.createElement('div');
            drugTag.className = 'selected-drug-tag';
            drugTag.innerHTML = `
                <span>${drug.name}</span>
                <span class="remove-drug" data-name="${drug.name}">&times;</span>
            `;
            selectedDrugsList.appendChild(drugTag);
        });
    };

    const fetchSuggestions = async (query) => {
        if (query.trim().length < 1) { 
            suggestionsList.innerHTML = '';
            return;
        }
        
        try {
            const response = await fetch(`${API_BASE_URL}/search_drugs/`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ query: query }),
            });
            const data = await response.json();
            
            suggestionsList.innerHTML = '';
            if (data.drugs && data.drugs.length > 0) {
                data.drugs.forEach(drug => {
                    const li = document.createElement('li');
                    li.textContent = drug.name;
                    li.addEventListener('click', () => addDrug(drug));
                    suggestionsList.appendChild(li);
                });
            } else {
                const li = document.createElement('li');
                li.textContent = 'ไม่พบยา';
                suggestionsList.appendChild(li);
            }
        } catch (error) {
            console.error('Error fetching suggestions:', error);
            suggestionsList.innerHTML = '<li>ข้อผิดพลาดในการดึงข้อมูล</li>';
        }
    };

    const checkInteractions = async () => {
        loadingEl.classList.remove('hidden');
        resultsEl.innerHTML = '';

        try {
            const drugNames = selectedDrugs.map(d => d.name);
            const response = await fetch(`${API_BASE_URL}/check_interactions/`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ drugs: drugNames }),
            });
            const data = await response.json();
            
            loadingEl.classList.add('hidden');
            
            if (data.interactions && data.interactions.length > 0) {
                data.interactions.forEach(interaction => {
                    const card = document.createElement('div');
                    card.className = `interaction-card severity-${interaction.severity.toLowerCase()}`;
                    card.innerHTML = `
                        <div class="interaction-title">${interaction.drug1} + ${interaction.drug2} (${interaction.severity_th})</div>
                        <p class="interaction-description"><strong>คำอธิบาย:</strong> ${interaction.description_th}</p>
                        <p class="interaction-description-en"><strong>English:</strong> ${interaction.description}</p>
                    `;
                    resultsEl.appendChild(card);
                });
            } else {
                resultsEl.innerHTML = '<div class="interaction-card severity-none">ไม่พบปฏิกิริยายาที่มีนัยสำคัญ</div>';
            }
        } catch (error) {
            console.error('Error checking interactions:', error);
            loadingEl.classList.add('hidden');
            resultsEl.innerHTML = '<div class="interaction-card severity-error">เกิดข้อผิดพลาดในการตรวจสอบปฏิกิริยา</div>';
        }
    };
    
    const checkBackendHealth = async () => {
        try {
            const response = await fetch(`${API_BASE_URL}/health`);
            if (response.ok) {
                statusDot.classList.add('status-connected');
                statusDot.classList.remove('status-error');
                statusText.textContent = 'เชื่อมต่อแล้ว';
            } else {
                statusDot.classList.add('status-error');
                statusDot.classList.remove('status-connected');
                statusText.textContent = 'ข้อผิดพลาด';
            }
        } catch (error) {
            statusDot.classList.add('status-error');
            statusDot.classList.remove('status-connected');
            statusText.textContent = 'ข้อผิดพลาด';
        }
    };
    
    checkBackendHealth();

    drugInput.addEventListener('input', (e) => {
        clearTimeout(timeoutId);
        const query = e.target.value.trim();
        timeoutId = setTimeout(() => {
            if (query) {
                fetchSuggestions(query);
            } else {
                suggestionsList.innerHTML = '';
            }
        }, 300);
    });

    selectedDrugsList.addEventListener('click', (e) => {
        if (e.target.classList.contains('remove-drug')) {
            const drugName = e.target.dataset.name;
            removeDrug(drugName);
        }
    });

    checkBtn.addEventListener('click', checkInteractions);

    clearBtn.addEventListener('click', () => {
        selectedDrugs = [];
        renderSelectedDrugs();
        updateCheckButtonState();
        resultsEl.innerHTML = '';
        drugInput.value = '';
    });
});