// One Play a Day - App Logic

// Default tags for the system
const DEFAULT_TAGS = [
  'RZ', 'Trick Play', 'OZ', 'IZ', 'RPO', 
  'Lateral', 'Pylon Sail', 'QB Run', 'Scissors'
];

class PlayGallery {
  constructor() {
    this.allPlays = [];
    this.filteredPlays = [];
    this.currentPage = 1;
    this.playsPerPage = 10;
    this.videoObserver = null;
    this.filters = {
      search: '',
      team: '',
      source: '',
      down: '',
      personnel: '',
      formation: '',
      playCaller: '',
      dateFrom: '',
      dateTo: '',
      tags: [] // Selected tags for filtering
    };
    this.teamMap = new Map(); // Maps play_number to extracted team
    this.playCallerLookup = new Map(); // Maps year|team to play caller
    this.userTags = this.loadUserTags(); // Load user tags from localStorage
    this.allTags = [...DEFAULT_TAGS]; // Will be populated with user-created tags too
    this.currentTaggingPlay = null; // Track which play is being tagged
    this.init();
  }

  async init() {
    try {
      await this.loadPlays();
      await this.loadPlayCallers();
      this.extractTeams();
      this.buildPlayCallerLookup();
      this.collectAllTags();
      this.setupVideoLazyLoading();
      this.setupFilters();
      this.setupTagging();
      this.setupTagFilter();
      this.populateFilterOptions();
      this.applyFilters();
      this.renderPage();
      this.updatePlayCount();
    } catch (error) {
      console.error('Error initializing gallery:', error);
      document.getElementById('plays-container').innerHTML = 
        '<div class="loading">Error loading plays. Please refresh the page.</div>';
    }
  }

  // ========== Tagging System ==========

  loadUserTags() {
    try {
      return JSON.parse(localStorage.getItem('opad-user-tags') || '{}');
    } catch {
      return {};
    }
  }

  saveUserTags() {
    localStorage.setItem('opad-user-tags', JSON.stringify(this.userTags));
  }

  collectAllTags() {
    // Combine default tags with any user-created tags
    const customTags = new Set();
    Object.values(this.userTags).forEach(tags => {
      tags.forEach(tag => customTags.add(tag));
    });
    
    // Merge with defaults, keeping unique
    const allTagsSet = new Set([...DEFAULT_TAGS, ...customTags]);
    this.allTags = [...allTagsSet].sort();
  }

  getPlayId(play) {
    // Get unique ID for a play (for localStorage key)
    return play.id || `play-${play.play_number}`;
  }

  getTagsForPlay(play) {
    const playId = this.getPlayId(play);
    return this.userTags[playId] || [];
  }

  fuzzyMatch(text, query) {
    if (!query) return true;
    const q = query.toLowerCase();
    const t = text.toLowerCase();
    return t.includes(q) || t.split(' ').some(word => word.startsWith(q));
  }

  setupTagging() {
    const backdrop = document.getElementById('tag-modal-backdrop');
    const closeBtn = document.getElementById('tag-modal-close');
    const cancelBtn = document.getElementById('tag-modal-cancel');
    const saveBtn = document.getElementById('tag-modal-save');
    const searchInput = document.getElementById('tag-modal-search');
    const addBtn = document.getElementById('tag-modal-add');
    const optionsContainer = document.getElementById('tag-modal-options');

    // Close modal handlers
    const closeModal = () => {
      backdrop.setAttribute('aria-hidden', 'true');
      this.currentTaggingPlay = null;
    };

    backdrop.addEventListener('click', (e) => {
      if (e.target === backdrop) closeModal();
    });
    closeBtn.addEventListener('click', closeModal);
    cancelBtn.addEventListener('click', closeModal);

    // Search/filter tags in modal
    searchInput.addEventListener('input', () => {
      this.renderTagModalOptions(searchInput.value);
    });

    // Add new tag
    addBtn.addEventListener('click', () => {
      const newTag = searchInput.value.trim();
      if (newTag && !this.allTags.includes(newTag)) {
        this.allTags.push(newTag);
        this.allTags.sort();
      }
      if (newTag) {
        this.toggleTagInModal(newTag);
        searchInput.value = '';
        this.renderTagModalOptions('');
      }
    });

    // Enter to add tag
    searchInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        addBtn.click();
      }
    });

    // Save tags
    saveBtn.addEventListener('click', () => {
      if (this.currentTaggingPlay) {
        const playId = this.getPlayId(this.currentTaggingPlay);
        const selectedTags = this.getModalSelectedTags();
        
        if (selectedTags.length > 0) {
          this.userTags[playId] = selectedTags;
        } else {
          delete this.userTags[playId];
        }
        
        this.saveUserTags();
        this.collectAllTags();
        this.renderPage(); // Re-render to show tags
        this.updateTagFilterOptions();
      }
      closeModal();
    });

    // Delegate click on tag options
    optionsContainer.addEventListener('click', (e) => {
      const pill = e.target.closest('.tag-pill');
      if (pill) {
        this.toggleTagInModal(pill.dataset.tag);
      }
    });
  }

  openTagModal(play) {
    this.currentTaggingPlay = play;
    const backdrop = document.getElementById('tag-modal-backdrop');
    const subtitle = document.getElementById('tag-modal-subtitle');
    const searchInput = document.getElementById('tag-modal-search');
    
    // Set subtitle to play title
    subtitle.textContent = play.title || 'Untitled Play';
    
    // Clear search
    searchInput.value = '';
    
    // Render current state
    this.renderTagModalSelected();
    this.renderTagModalOptions('');
    
    // Show modal
    backdrop.setAttribute('aria-hidden', 'false');
    searchInput.focus();
  }

  renderTagModalSelected() {
    const container = document.getElementById('tag-modal-selected');
    const tags = this.currentTaggingPlay ? this.getTagsForPlay(this.currentTaggingPlay) : [];
    
    if (tags.length === 0) {
      container.innerHTML = '<span class="tag-modal-empty">No tags selected</span>';
      return;
    }
    
    container.innerHTML = tags.map(tag => `
      <span class="tag-pill tag-pill-selected" data-tag="${this.escapeHtml(tag)}">
        ${this.escapeHtml(tag)} <span class="tag-remove">×</span>
      </span>
    `).join('');
    
    // Handle remove clicks
    container.querySelectorAll('.tag-pill').forEach(pill => {
      pill.addEventListener('click', () => {
        this.toggleTagInModal(pill.dataset.tag);
      });
    });
  }

  renderTagModalOptions(query) {
    const container = document.getElementById('tag-modal-options');
    const currentTags = this.currentTaggingPlay ? this.getTagsForPlay(this.currentTaggingPlay) : [];
    
    const filtered = this.allTags.filter(tag => 
      this.fuzzyMatch(tag, query) && !currentTags.includes(tag)
    );
    
    if (filtered.length === 0) {
      container.innerHTML = query 
        ? '<span class="tag-modal-empty">No matching tags. Press Enter to create.</span>'
        : '<span class="tag-modal-empty">All tags selected</span>';
      return;
    }
    
    container.innerHTML = filtered.map(tag => `
      <span class="tag-pill" data-tag="${this.escapeHtml(tag)}">${this.escapeHtml(tag)}</span>
    `).join('');
  }

  toggleTagInModal(tag) {
    if (!this.currentTaggingPlay) return;
    
    const playId = this.getPlayId(this.currentTaggingPlay);
    const currentTags = this.userTags[playId] || [];
    
    if (currentTags.includes(tag)) {
      this.userTags[playId] = currentTags.filter(t => t !== tag);
    } else {
      this.userTags[playId] = [...currentTags, tag];
    }
    
    this.renderTagModalSelected();
    this.renderTagModalOptions(document.getElementById('tag-modal-search').value);
  }

  getModalSelectedTags() {
    if (!this.currentTaggingPlay) return [];
    return this.userTags[this.getPlayId(this.currentTaggingPlay)] || [];
  }

  // ========== Tag Filter ==========

  setupTagFilter() {
    const input = document.getElementById('tag-filter-input');
    const optionsContainer = document.getElementById('tag-filter-options');
    const selectedContainer = document.getElementById('tag-filter-selected');

    // Show options on focus
    input.addEventListener('focus', () => {
      this.renderTagFilterOptions(input.value);
      optionsContainer.style.display = 'block';
    });

    // Hide options on blur (with delay for click)
    input.addEventListener('blur', () => {
      setTimeout(() => {
        optionsContainer.style.display = 'none';
      }, 200);
    });

    // Filter as user types
    input.addEventListener('input', () => {
      this.renderTagFilterOptions(input.value);
    });

    // Handle option clicks
    optionsContainer.addEventListener('click', (e) => {
      const pill = e.target.closest('.tag-pill');
      if (pill) {
        this.toggleFilterTag(pill.dataset.tag);
        input.value = '';
      }
    });

    // Handle selected tag removal
    selectedContainer.addEventListener('click', (e) => {
      const pill = e.target.closest('.tag-pill');
      if (pill) {
        this.toggleFilterTag(pill.dataset.tag);
      }
    });

    this.updateTagFilterOptions();
  }

  renderTagFilterOptions(query) {
    const container = document.getElementById('tag-filter-options');
    const filtered = this.allTags.filter(tag => 
      this.fuzzyMatch(tag, query) && !this.filters.tags.includes(tag)
    );
    
    if (filtered.length === 0) {
      container.innerHTML = '<span class="tag-filter-empty">No matching tags</span>';
      return;
    }
    
    container.innerHTML = filtered.map(tag => `
      <span class="tag-pill" data-tag="${this.escapeHtml(tag)}">${this.escapeHtml(tag)}</span>
    `).join('');
  }

  updateTagFilterOptions() {
    this.renderTagFilterSelected();
    this.renderTagFilterOptions('');
  }

  renderTagFilterSelected() {
    const container = document.getElementById('tag-filter-selected');
    
    if (this.filters.tags.length === 0) {
      container.innerHTML = '';
      return;
    }
    
    container.innerHTML = this.filters.tags.map(tag => `
      <span class="tag-pill tag-pill-selected" data-tag="${this.escapeHtml(tag)}">
        ${this.escapeHtml(tag)} <span class="tag-remove">×</span>
      </span>
    `).join('');
  }

  toggleFilterTag(tag) {
    if (this.filters.tags.includes(tag)) {
      this.filters.tags = this.filters.tags.filter(t => t !== tag);
    } else {
      this.filters.tags.push(tag);
    }
    this.updateTagFilterOptions();
    this.applyFilters();
  }

  async loadPlays() {
    const response = await fetch('plays.json');
    this.allPlays = await response.json();
    // Sort by date descending (newest first), then by play_number/id within same date
    this.allPlays.sort((a, b) => {
      // Primary: sort by date descending
      const dateA = new Date(a.date || '1970-01-01');
      const dateB = new Date(b.date || '1970-01-01');
      if (dateB - dateA !== 0) return dateB - dateA;
      
      // Secondary: within same date, sort by play_number or tweet id descending
      const aIsTwitter = a.source === 'twitter' || (a.id && a.id.startsWith('x-'));
      const bIsTwitter = b.source === 'twitter' || (b.id && b.id.startsWith('x-'));
      
      if (aIsTwitter && bIsTwitter) {
        const aId = a.id.replace('x-', '');
        const bId = b.id.replace('x-', '');
        return bId.localeCompare(aId);
      }
      
      return (b.play_number || 0) - (a.play_number || 0);
    });
    this.filteredPlays = [...this.allPlays];
  }

  async loadPlayCallers() {
    try {
      const response = await fetch('data/play-callers.json');
      this.playCallersData = await response.json();
    } catch (error) {
      console.warn('Play caller data unavailable, continuing without it.', error);
      this.playCallersData = null;
    }
  }

  /**
   * Extract team names from play titles
   * Pattern: "YEAR Team doing..." e.g., "2025 Utah using...", "2025 Chiefs running..."
   */
  extractTeams() {
    const teamSet = new Set();
    
    // Common action verbs that signal end of team name
    const actionWords = ['running', 'using', 'keeping', 'lining', 'throwing', 'short', 
                         'Defense', 'taking', 'getting', 'motioning'];
    
    this.allPlays.forEach(play => {
      if (play.title && play.title !== 'Untitled Play') {
        // Try to extract team: "YEAR TeamName action..."
        const match = play.title.match(/^(\d{4})\s+(.+?)\s+(running|using|keeping|lining|throwing|short|Defense|taking|getting|motioning)/i);
        
        if (match) {
          let team = match[2].trim();
          // Normalize some team names
          team = this.normalizeTeamName(team);
          this.teamMap.set(play.play_number, team);
          teamSet.add(team);
        }
      }
    });

    // Store sorted teams for dropdown
    this.teams = [...teamSet].sort();
  }

  normalizeTeamName(team) {
    // Handle some edge cases and normalize names
    const normalizations = {
      '49ers': 'San Francisco 49ers',
      'Vikings Defense': 'Minnesota Vikings',
      'Indiana Defense': 'Indiana',
    };
    
    // Remove trailing "Defense" if present
    team = team.replace(/\s+Defense$/i, '');
    
    return normalizations[team] || team;
  }

  getTeamForPlay(play) {
    return this.teamMap.get(play.play_number) || '';
  }

  buildPlayCallerLookup() {
    if (!this.playCallersData) return;

    const leagues = ['nfl', 'college'];
    leagues.forEach(league => {
      const leagueData = this.playCallersData[league] || {};
      Object.entries(leagueData).forEach(([year, teams]) => {
        Object.entries(teams || {}).forEach(([team, info]) => {
          if (!info || !info.playCaller) return;
          const normalizedTeam = this.normalizeTeamName(team);
          const key = `${year}|${normalizedTeam}`;
          this.playCallerLookup.set(key, info.playCaller);
        });
      });
    });
  }

  getPlayYear(play) {
    if (play.date) return play.date.slice(0, 4);
    const match = play.title?.match(/^(\d{4})/);
    return match ? match[1] : '';
  }

  extractPlayCallerFromTitle(title) {
    if (!title) return '';

    // Only capture parenthetical that appears before the action verb.
    const match = title.match(
      /^\d{4}\s+.+?\s+\(([^)]+)\)\s+(running|using|keeping|lining|throwing|short|Defense|taking|getting|motioning)\b/i
    );

    if (!match) return '';

    const candidate = match[1].trim();

    // Exclude all-caps or shorthand qualifiers like (FL), (OK), (FCS - NC).
    if (/^[A-Z0-9\s&/.-]+$/.test(candidate)) return '';

    return candidate;
  }

  getPlayCallerForPlay(play) {
    const directCaller = play.play_caller || play.playCaller || play.play_details?.play_caller;
    if (directCaller) return directCaller;

    const titleCaller = this.extractPlayCallerFromTitle(play.title);
    if (titleCaller) return titleCaller;

    const year = this.getPlayYear(play);
    const team = this.getTeamForPlay(play);
    if (!year || !team) return '';

    return this.playCallerLookup.get(`${year}|${team}`) || '';
  }

  setupFilters() {
    // Search input with debounce
    const searchInput = document.getElementById('search-input');
    let debounceTimer;
    searchInput.addEventListener('input', (e) => {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(() => {
        this.filters.search = e.target.value.toLowerCase();
        this.applyFilters();
      }, 300);
    });

    // Team filter
    document.getElementById('team-filter').addEventListener('change', (e) => {
      this.filters.team = e.target.value;
      this.applyFilters();
    });

    // Source filter
    document.getElementById('source-filter').addEventListener('change', (e) => {
      this.filters.source = e.target.value;
      this.applyFilters();
    });

    // Down filter
    document.getElementById('down-filter').addEventListener('change', (e) => {
      this.filters.down = e.target.value;
      this.applyFilters();
    });

    // Personnel filter
    document.getElementById('personnel-filter').addEventListener('change', (e) => {
      this.filters.personnel = e.target.value;
      this.applyFilters();
    });

    // Formation filter
    document.getElementById('formation-filter').addEventListener('change', (e) => {
      this.filters.formation = e.target.value;
      this.applyFilters();
    });

    // Play caller filter
    document.getElementById('caller-filter').addEventListener('change', (e) => {
      this.filters.playCaller = e.target.value;
      this.applyFilters();
    });

    // Date range filters
    document.getElementById('date-from').addEventListener('change', (e) => {
      this.filters.dateFrom = e.target.value;
      this.applyFilters();
    });

    document.getElementById('date-to').addEventListener('change', (e) => {
      this.filters.dateTo = e.target.value;
      this.applyFilters();
    });

    // Clear filters button
    document.getElementById('clear-filters').addEventListener('click', () => {
      this.clearFilters();
    });
  }

  populateFilterOptions() {
    // Populate team dropdown
    const teamSelect = document.getElementById('team-filter');
    this.teams.forEach(team => {
      const option = document.createElement('option');
      option.value = team;
      option.textContent = team;
      teamSelect.appendChild(option);
    });

    // Extract unique personnel and formations
    const personnelSet = new Set();
    const formationSet = new Set();
    const playCallerSet = new Set();

    this.allPlays.forEach(play => {
      if (play.play_details?.personnel) {
        personnelSet.add(play.play_details.personnel);
      }
      if (play.play_details?.formation) {
        formationSet.add(play.play_details.formation);
      }
      const playCaller = this.getPlayCallerForPlay(play);
      if (playCaller) {
        playCallerSet.add(playCaller);
      }
    });

    // Sort and populate personnel dropdown
    const personnelSelect = document.getElementById('personnel-filter');
    [...personnelSet].sort().forEach(personnel => {
      const option = document.createElement('option');
      option.value = personnel;
      option.textContent = personnel;
      personnelSelect.appendChild(option);
    });

    // Sort and populate formation dropdown
    const formationSelect = document.getElementById('formation-filter');
    [...formationSet].sort().forEach(formation => {
      const option = document.createElement('option');
      option.value = formation;
      option.textContent = formation;
      formationSelect.appendChild(option);
    });

    // Sort and populate play caller dropdown
    const callerSelect = document.getElementById('caller-filter');
    [...playCallerSet].sort().forEach(playCaller => {
      const option = document.createElement('option');
      option.value = playCaller;
      option.textContent = playCaller;
      callerSelect.appendChild(option);
    });

    // Set date range bounds based on data
    this.setDateRangeBounds();
  }

  setDateRangeBounds() {
    const dates = this.allPlays
      .map(p => p.date)
      .filter(d => d)
      .sort();
    
    if (dates.length > 0) {
      const dateFrom = document.getElementById('date-from');
      const dateTo = document.getElementById('date-to');
      
      dateFrom.min = dates[0];
      dateFrom.max = dates[dates.length - 1];
      dateTo.min = dates[0];
      dateTo.max = dates[dates.length - 1];
    }
  }

  applyFilters() {
    this.filteredPlays = this.allPlays.filter(play => {
      // Search filter (title - searches full title for team names, play concepts, etc.)
      if (this.filters.search) {
        const searchTerm = this.filters.search;
        const titleMatch = play.title.toLowerCase().includes(searchTerm);
        const personnelMatch = play.play_details?.personnel?.toLowerCase().includes(searchTerm);
        const formationMatch = play.play_details?.formation?.toLowerCase().includes(searchTerm);
        
        if (!titleMatch && !personnelMatch && !formationMatch) return false;
      }

      // Team filter
      if (this.filters.team) {
        const playTeam = this.getTeamForPlay(play);
        if (playTeam !== this.filters.team) return false;
      }

      // Source filter
      if (this.filters.source) {
        const isTwitter = play.source === 'twitter' || (play.id && play.id.startsWith('x-'));
        if (this.filters.source === 'twitter' && !isTwitter) return false;
        if (this.filters.source === 'email' && isTwitter) return false;
      }

      // Down filter
      if (this.filters.down) {
        const downMatch = play.play_details?.down_and_distance?.startsWith(this.filters.down);
        if (!downMatch) return false;
      }

      // Personnel filter
      if (this.filters.personnel) {
        if (play.play_details?.personnel !== this.filters.personnel) return false;
      }

      // Formation filter
      if (this.filters.formation) {
        if (play.play_details?.formation !== this.filters.formation) return false;
      }

      // Play caller filter
      if (this.filters.playCaller) {
        const playCaller = this.getPlayCallerForPlay(play);
        if (playCaller !== this.filters.playCaller) return false;
      }

      // Date range filter
      if (this.filters.dateFrom) {
        if (!play.date || play.date < this.filters.dateFrom) return false;
      }
      if (this.filters.dateTo) {
        if (!play.date || play.date > this.filters.dateTo) return false;
      }

      // Tag filter - match ANY selected tag
      if (this.filters.tags.length > 0) {
        const playTags = this.getTagsForPlay(play);
        const hasMatchingTag = this.filters.tags.some(tag => playTags.includes(tag));
        if (!hasMatchingTag) return false;
      }

      return true;
    });

    this.currentPage = 1;
    this.renderPage();
    this.updateFilterCount();
  }

  clearFilters() {
    this.filters = { 
      search: '', 
      team: '',
      source: '',
      down: '', 
      personnel: '', 
      formation: '',
      playCaller: '',
      dateFrom: '',
      dateTo: '',
      tags: []
    };
    
    document.getElementById('search-input').value = '';
    document.getElementById('team-filter').value = '';
    document.getElementById('source-filter').value = '';
    document.getElementById('down-filter').value = '';
    document.getElementById('personnel-filter').value = '';
    document.getElementById('formation-filter').value = '';
    document.getElementById('caller-filter').value = '';
    document.getElementById('date-from').value = '';
    document.getElementById('date-to').value = '';
    document.getElementById('tag-filter-input').value = '';
    
    this.updateTagFilterOptions();
    this.applyFilters();
  }

  updateFilterCount() {
    const countEl = document.getElementById('filter-count');
    const isFiltered = Object.values(this.filters).some(v => v);
    
    if (isFiltered) {
      countEl.textContent = `Showing ${this.filteredPlays.length} of ${this.allPlays.length} plays`;
      countEl.style.display = 'block';
    } else {
      countEl.style.display = 'none';
    }
  }

  setupVideoLazyLoading() {
    // Use IntersectionObserver to lazy load videos
    const options = {
      root: null,
      rootMargin: '50px',
      threshold: 0.1
    };

    this.videoObserver = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          const video = entry.target;
          const src = video.dataset.src;
          
          if (src && !video.src) {
            video.src = src;
            video.load();
            video.classList.add('loaded');
          }
          
          this.videoObserver.unobserve(video);
        }
      });
    }, options);
  }

  renderPage() {
    const container = document.getElementById('plays-container');
    const start = (this.currentPage - 1) * this.playsPerPage;
    const end = start + this.playsPerPage;
    const playsToShow = this.filteredPlays.slice(start, end);

    if (playsToShow.length === 0) {
      const isFiltered = Object.values(this.filters).some(v => v);
      container.innerHTML = isFiltered 
        ? '<div class="loading">No plays match your filters. Try adjusting your search.</div>'
        : '<div class="loading">No plays to display.</div>';
      return;
    }

    // Split plays by quarter if play object includes quarter info (e.g., play.quarter)
    let quarterSections = {};
    playsToShow.forEach(play => {
      const q = play.quarter || 1; // Default to Q1 if not present
      if (!quarterSections[q]) quarterSections[q] = [];
      quarterSections[q].push(play);
    });

    // Compose HTML by quarter
    let cardsHtml = '';
    Object.keys(quarterSections).sort((a,b)=>a-b).forEach(q => {
      cardsHtml += `<div class=\"quarter-section\"><h3>Q${q}</h3><div class=\"quarter-narrative\">${this.generateQuarterNarrative(Number(q))}</div>`;
      cardsHtml += quarterSections[q].map(play => this.createPlayCard(play)).join('');
      cardsHtml += '</div>';
    });

    container.innerHTML = cardsHtml;

    // Set up lazy loading for videos on this page
    const videos = container.querySelectorAll('video[data-src]');
    videos.forEach(video => this.videoObserver.observe(video));

    // Set up tag button handlers
    container.querySelectorAll('.tag-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.preventDefault();
        const playId = btn.dataset.playId;
        const play = this.allPlays.find(p => this.getPlayId(p) === playId);
        if (play) {
          this.openTagModal(play);
        }
      });
    });

    this.updatePagination();
    
    // Scroll to top of plays
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  createPlayCard(play) {
    const date = new Date(play.date).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric'
    });

    // Support both old and new data formats
    const angles = play.angles || [play.play_video_angle_1, play.play_video_angle_2].filter(Boolean);
    const angleCount = angles.length;
    const containerClass = angleCount === 2 ? 'videos-container-two' : 'videos-container-multi';

    // Get team for badge display
    const team = this.getTeamForPlay(play);

    const videoHTML = angles.map((anglePath, index) => `
      <div class="video-wrapper">
        <span class="video-label">Angle ${index + 1}</span>
        <video 
          data-src="${anglePath}"
          autoplay 
          loop 
          muted 
          playsinline
          class="lazy-load"
          preload="none">
          Your browser does not support the video tag.
        </video>
      </div>
    `).join('');

    // Determine source and ID display
    const isTwitter = play.source === 'twitter' || (play.id && play.id.startsWith('x-'));
    const playIdDisplay = isTwitter ? 'X' : `#${play.play_number}`;
    const sourceClass = isTwitter ? 'source-twitter' : 'source-email';
    const twitterLink = play.twitter_url ? `<a href="${play.twitter_url}" target="_blank" class="twitter-link" title="View on X">🔗</a>` : '';

    // Get user tags for this play
    const userTags = this.getTagsForPlay(play);
    const tagsHTML = userTags.length > 0 
      ? `<div class="play-tags">${userTags.map(t => `<span class="tag-pill tag-pill-small">${this.escapeHtml(t)}</span>`).join('')}</div>`
      : '';
    
    const playId = this.getPlayId(play);

    // Penalty detection: check for penalty tags
    const PENALTY_TAGS = [
      'Penalty', 'PI', 'Pass Interference', 'Holding', 'Personal Foul', 
      'Unsportsmanlike', 'Offside', 'False Start', 'Flag', 'Face Mask', 
      'Roughing', 'Delay of Game', 'Encroachment', 'Illegal', 'Targeting', 'Disqualified'
    ];
    // Lowercase for robust matching
    const allTags = (play.auto_tags || []).concat(this.getTagsForPlay(play) || []).map(t => (t || '').toLowerCase());
    const hasPenalty = allTags.some(tag => PENALTY_TAGS.some(penTag => tag.includes(penTag.toLowerCase())));
    const penaltyIconHTML = hasPenalty ? `<span title="Penalty" class="penalty-flag" style="margin-left:8px;color:red;font-size:1.5em;">🚩</span>` : '';

    return `
      <article class="play-card ${sourceClass}" data-play-id="${playId}">
        <div class="card-header">
          <div class="play-meta">
            <span class="play-number">${playIdDisplay}</span>
            ${team ? `<span class="team-badge">${this.escapeHtml(team)}</span>` : ''}
            <span class="play-date">${date}</span>
            ${twitterLink}
            <button class="tag-btn" data-play-id="${playId}" title="Tag this play">🏷️</button>
            ${penaltyIconHTML}
          </div>
          <h2 class="play-title">${this.escapeHtml(play.title)}</h2>
          ${tagsHTML}
        </div>

        <div class="play-details">
          <div class="detail-item">
            <span class="detail-label">Down & Distance</span>
            <span class="detail-value">${this.escapeHtml(play.play_details.down_and_distance)}</span>
          </div>
          <div class="detail-item">
            <span class="detail-label">Personnel</span>
            <span class="detail-value">${this.escapeHtml(play.play_details.personnel)}</span>
          </div>
          <div class="detail-item">
            <span class="detail-label">Formation</span>
            <span class="detail-value">${this.escapeHtml(play.play_details.formation)}</span>
          </div>
        </div>

        <div class="video-section">
          ${youtubeEmbedHTML}
          <div class="videos-container ${containerClass}">
            ${videoHTML}
          </div>
          <div class="diagram-wrapper">
            <span class="diagram-label">Play Diagram</span>
            <img 
              src="${play.play_diagram}" 
              alt="Play diagram for ${this.escapeHtml(play.title)}"
              class="play-diagram"
              loading="lazy">
          </div>
        </div>
      </article>
    `;
  }

  updatePagination() {
    const totalPages = Math.ceil(this.filteredPlays.length / this.playsPerPage);
    
    document.getElementById('prev-btn').disabled = this.currentPage === 1;
    document.getElementById('next-btn').disabled = this.currentPage === totalPages || totalPages === 0;
    document.getElementById('page-info').textContent = 
      `Page ${this.currentPage} of ${totalPages || 1}`;
  }

  updatePlayCount() {
    document.getElementById('play-count').textContent = 
      `${this.allPlays.length} ${this.allPlays.length === 1 ? 'Play' : 'Plays'}`;
  }

  nextPage() {
    const totalPages = Math.ceil(this.filteredPlays.length / this.playsPerPage);
    if (this.currentPage < totalPages) {
      this.currentPage++;
      this.renderPage();
    }
  }

  prevPage() {
    if (this.currentPage > 1) {
      this.currentPage--;
      this.renderPage();
    }
  }

  escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text || '';
    return div.innerHTML;
  }
}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
  const gallery = new PlayGallery();

  // Set up pagination button listeners
  document.getElementById('prev-btn').addEventListener('click', () => gallery.prevPage());
  document.getElementById('next-btn').addEventListener('click', () => gallery.nextPage());
});

    // If provided: support optional YouTube URL and timestamp fields for inline embeds
    const hasYouTube = !!play.youtube_url;
    let youtubeEmbedHTML = '';
    if (hasYouTube) {
      let videoId = '';
      const match = play.youtube_url && play.youtube_url.match(/[?&]v=([^&]+)/);
      if (match) {
        videoId = match[1];
      } else if (play.youtube_url && play.youtube_url.includes('youtu.be/')) {
        videoId = play.youtube_url.split('youtu.be/')[1].split(/[&#?]/)[0];
      }
      let startTime = 0;
      if (typeof play.youtube_timestamp === 'number') {
        startTime = play.youtube_timestamp;
      } else if (play.youtube_url && play.youtube_url.includes('t=')) {
        const tMatch = play.youtube_url.match(/[?&]t=(\d+)/);
        if (tMatch) startTime = Number(tMatch[1]);
      }
      if (videoId) {
        youtubeEmbedHTML = `<div class=\"youtube-embed-wrapper\">\n          <iframe width=\"420\" height=\"236\"\n            src=\"https://www.youtube.com/embed/${videoId}${startTime ? '?start=' + startTime : ''}\"\n            title=\"YouTube video player\"\n            frameborder=\"0\"\n            allow=\"accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share\"\n            allowfullscreen></iframe>\n        </div>`;
      }
    }
  // ========== Narrative/Storytelling Stub ==========
  // In v2, this would call LLM or advanced narrative generator.
  // Here we simply hardcode a sample for demo/testing.
  generateQuarterNarrative(quarter) {
    // TODO: LLM-generated logic; for now just dummy text per quarter
    const demos = {
      1: "Quarter 1: Both teams started slow. Defenses set the tone early, with key 3rd down stops and a field position battle.",
      2: "Quarter 2: Offenses found rhythm mid-way as Indiana hit a 40-yard TD, only for Miami to answer late. Critical penalty swung momentum before halftime.",
      3: "Quarter 3: Miami took control after a controversial call but Indiana struck back with explosive plays and a big turnover.",
      4: "Quarter 4: The finish delivered drama—a game-winning drive, lead changes, and a walk-off FG attempt decided the champion."
    };
    return demos[quarter] || "No summary available for this quarter.";
  }
