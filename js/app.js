// One Play a Day - App Logic

class PlayGallery {
  constructor() {
    this.plays = [];
    this.currentPage = 1;
    this.playsPerPage = 10;
    this.videoObserver = null;
    this.init();
  }

  async init() {
    try {
      await this.loadPlays();
      this.setupVideoLazyLoading();
      this.renderPage();
      this.updatePlayCount();
    } catch (error) {
      console.error('Error initializing gallery:', error);
      document.getElementById('plays-container').innerHTML = 
        '<div class="loading">Error loading plays. Please refresh the page.</div>';
    }
  }

  async loadPlays() {
    const response = await fetch('plays.json');
    this.plays = await response.json();
    // Sort by play number descending (most recent first)
    this.plays.sort((a, b) => b.play_number - a.play_number);
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
    const playsToShow = this.plays.slice(start, end);

    if (playsToShow.length === 0) {
      container.innerHTML = '<div class="loading">No plays to display.</div>';
      return;
    }

    container.innerHTML = playsToShow.map(play => this.createPlayCard(play)).join('');

    // Set up lazy loading for videos on this page
    const videos = container.querySelectorAll('video[data-src]');
    videos.forEach(video => this.videoObserver.observe(video));

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

    return `
      <article class="play-card">
        <div class="card-header">
          <div class="play-meta">
            <span class="play-number">Play #${play.play_number}</span>
            <span class="play-date">${date}</span>
          </div>
          <h2 class="play-title">${this.escapeHtml(play.title)}</h2>
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
    const totalPages = Math.ceil(this.plays.length / this.playsPerPage);
    
    document.getElementById('prev-btn').disabled = this.currentPage === 1;
    document.getElementById('next-btn').disabled = this.currentPage === totalPages;
    document.getElementById('page-info').textContent = 
      `Page ${this.currentPage} of ${totalPages}`;
  }

  updatePlayCount() {
    document.getElementById('play-count').textContent = 
      `${this.plays.length} ${this.plays.length === 1 ? 'Play' : 'Plays'}`;
  }

  nextPage() {
    const totalPages = Math.ceil(this.plays.length / this.playsPerPage);
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
    div.textContent = text;
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
