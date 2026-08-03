/**
 * gemini.js
 * =========
 * JavaScript client for the Gemini web UI API (cookie-based, no official API key needed).
 *
 * FIXES applied:
 *  - Updated `bl=` build label to 2024 value (was 2023, which is broken).
 *  - Improved response parser that correctly handles the wrb.fr JSON wrapper format.
 *  - Added image URL extraction from response content.
 *  - Better error messages and structured error returns.
 *  - Multi-turn conversation maintained across calls.
 *
 * Usage:
 *   const gemini = new Gemini('cookies.json');
 *   await gemini.initialize();
 *   const res = await gemini.ask("Hello!");
 *   console.log(res.content);
 */

const axios = require('axios');
const fs = require('fs').promises;

class Gemini {
  /**
   * @param {string} cookiePath   - Path to cookies JSON file
   * @param {number} timeout      - Request timeout in ms (default 30000)
   */
  constructor(cookiePath, timeout = 30000) {
    this.cookiePath = cookiePath;
    this.timeout = timeout;
    this.sessionAuth1 = '';
    this.sessionAuth2 = '';
    this.SNlM0e = '';
    this.conversationId = '';
    this.responseId = '';
    this.choiceId = '';
    this._reqid = Math.floor(Math.random() * 9000000) + 1000000;
  }

  async initialize() {
    await this.loadCookies();
    this.SNlM0e = await this.getSnlm0e();
    return this;
  }

  async loadCookies() {
    try {
      const cookieData = await fs.readFile(this.cookiePath, 'utf8');
      const cookies = JSON.parse(cookieData);
      this.sessionAuth1 = cookies.find(c => c.name === '__Secure-1PSID')?.value;
      this.sessionAuth2 = cookies.find(c => c.name === '__Secure-1PSIDTS')?.value;

      if (!this.sessionAuth1) {
        throw new Error('__Secure-1PSID cookie not found in cookie file.');
      }
      if (!this.sessionAuth2) {
        throw new Error('__Secure-1PSIDTS cookie not found in cookie file.');
      }
    } catch (error) {
      throw new Error(`Failed to load cookies: ${error.message}`);
    }
  }

  async getSnlm0e() {
    try {
      const response = await axios.get('https://gemini.google.com/app', {
        timeout: 15000,
        headers: this.getHeaders(),
        maxRedirects: 5,
      });

      // Check for auth failure
      if (response.request?.res?.responseUrl?.includes('accounts.google.com')) {
        throw new Error('Authentication failed. Cookies are invalid or expired.');
      }

      // Try multiple patterns for SNlM0e extraction
      const patterns = [
        /["']SNlM0e["']\s*:\s*["'](.*?)["']/,
        /SNlM0e":"(.*?)"/,
      ];

      for (const pattern of patterns) {
        const match = response.data.match(pattern);
        if (match?.[1]) return match[1];
      }

      throw new Error(
        'SNlM0e token not found. Cookies may be invalid, expired, or rate-limited.'
      );
    } catch (error) {
      if (error.response?.status === 429) {
        throw new Error('Rate limited by Google. Please wait before retrying.');
      }
      if (error.response?.status === 401 || error.response?.status === 403) {
        throw new Error('Authentication failed. Please refresh your cookies.');
      }
      throw new Error(`Failed to retrieve SNlM0e: ${error.message}`);
    }
  }

  getHeaders() {
    return {
      'Content-Type': 'application/x-www-form-urlencoded;charset=utf-8',
      'Host': 'gemini.google.com',
      'Origin': 'https://gemini.google.com',
      'Referer': 'https://gemini.google.com/',
      'User-Agent':
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ' +
        '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
      'X-Same-Domain': '1',
      'Cookie': `__Secure-1PSID=${this.sessionAuth1}; __Secure-1PSIDTS=${this.sessionAuth2}`,
    };
  }

  /**
   * Send a message and return the full response.
   *
   * @param {string} question   - The message to send.
   * @returns {Promise<{content: string|null, conversationId: string, responseId: string, images: string[], error: boolean}>}
   */
  async ask(question) {
    try {
      // FIXED: Updated build label from 2023 → 2024
      const params = new URLSearchParams({
        bl: 'boq_assistant-bard-web-server_20240625.13_p0',
        _reqid: String(this._reqid),
        rt: 'c',
      });

      const messageStruct = [
        [question],
        null,
        [this.conversationId, this.responseId, this.choiceId],
      ];

      const postData = new URLSearchParams({
        'f.req': JSON.stringify([null, JSON.stringify(messageStruct)]),
        at: this.SNlM0e,
      });

      const response = await axios.post(
        `https://gemini.google.com/_/BardChatUi/data/assistant.lamda.BardFrontendService/StreamGenerate?${params}`,
        postData.toString(),
        {
          headers: this.getHeaders(),
          timeout: this.timeout,
        }
      );

      // FIXED: Updated parser to match the wrb.fr JSON wrapper format
      const result = this._parseResponse(response.data);
      if (result) {
        this.conversationId = result.conversationId || this.conversationId;
        this.responseId = result.responseId || this.responseId;
        this.choiceId = result.choiceId || this.choiceId;
        this._reqid += Math.floor(Math.random() * 8000) + 1000;
        return { ...result, error: false };
      }

      return { content: null, images: [], error: true, message: 'Failed to parse response.' };
    } catch (error) {
      console.error(`[Gemini] Error during ask: ${error.message}`);
      return { content: null, images: [], error: true, message: error.message };
    }
  }

  /**
   * Parse the multi-line StreamGenerate response body.
   * Handles the modern wrb.fr JSON wrapper format.
   *
   * @param {string} responseText - Raw response text from the API.
   * @returns {object|null} Parsed result or null on failure.
   */
  _parseResponse(responseText) {
    const lines = responseText.split('\n');

    for (const line of lines) {
      if (!line || line === ")]}'" || !line.startsWith('[')) continue;

      let jsonLine = line;
      if (jsonLine.startsWith(')]}"')) {
        jsonLine = jsonLine.slice(4).trim();
      }

      let outerArray;
      try {
        outerArray = JSON.parse(jsonLine);
      } catch {
        continue;
      }

      // Find the wrb.fr part which contains the actual response
      for (const part of outerArray) {
        if (!Array.isArray(part) || part.length < 3 || part[0] !== 'wrb.fr') {
          continue;
        }

        const innerStr = part[2];
        if (typeof innerStr !== 'string') continue;

        let body;
        try {
          body = JSON.parse(innerStr);
        } catch {
          continue;
        }

        if (!body || !body[4]) continue;

        try {
          // Extract main text content
          const content = body[4]?.[0]?.[1] ?? null;

          // Extract conversation metadata
          const conversationId = body[1]?.[0] ?? this.conversationId;
          const responseId = body[1]?.[1] ?? this.responseId;
          const choiceId = body[4]?.[0]?.[0] ?? this.choiceId;

          // Extract web images (format 1)
          const images = [];
          const imgData = body[4]?.[0]?.[4];
          if (Array.isArray(imgData)) {
            for (const img of imgData) {
              try {
                const url = img?.[0]?.[0]?.[0];
                if (url) images.push(url);
              } catch {
                // ignore malformed image entries
              }
            }
          }

          // Fallback: extract image URLs from text content
          if (images.length === 0 && content) {
            const urlMatches = content.match(/https?:\/\/[^\s"']+\.(jpg|jpeg|png|gif|webp)/gi);
            if (urlMatches) images.push(...urlMatches);
          }

          return { content, conversationId, responseId, choiceId, images };
        } catch (e) {
          console.error(`[Gemini] Parse error: ${e.message}`);
        }
      }
    }

    return null;
  }
}

module.exports = Gemini;

// ─────────────────────────────────────────────
// Example CLI usage
// ─────────────────────────────────────────────
if (require.main === module) {
  const readline = require('readline').createInterface({
    input: process.stdin,
    output: process.stdout,
  });

  (async () => {
    const gemini = new Gemini('cookies.json');
    try {
      await gemini.initialize();
      console.log('✅ Gemini initialized. Type your message:\n');
    } catch (err) {
      console.error(`❌ Init failed: ${err.message}`);
      process.exit(1);
    }

    const prompt = () => {
      readline.question('>>> ', async (question) => {
        if (!question.trim() || question === 'exit') {
          console.log('Bye!');
          readline.close();
          return;
        }
        const response = await gemini.ask(question);
        if (response.error) {
          console.error(`Error: ${response.message || 'Unknown error'}`);
        } else {
          console.log(`\nGemini: ${response.content}\n`);
          if (response.images.length > 0) {
            console.log('Images:', response.images);
          }
        }
        prompt(); // next turn
      });
    };

    prompt();
  })();
}
