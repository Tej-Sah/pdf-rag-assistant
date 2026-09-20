import { useState } from "react";
import "./App.css";

const API_URL = "http://127.0.0.1:8001";

function App() {
  const [file, setFile] = useState(null);
  const [question, setQuestion] = useState("");
  const [topK, setTopK] = useState(3);

  const [answer, setAnswer] = useState("");
  const [sources, setSources] = useState([]);

  const [uploading, setUploading] = useState(false);
  const [asking, setAsking] = useState(false);

  const [uploadMessage, setUploadMessage] = useState("");
  const [error, setError] = useState("");

  // =====================================================
  // SELECT FILE
  // =====================================================

  const handleFileChange = (event) => {
    const selectedFile = event.target.files[0];

    if (!selectedFile) {
      return;
    }

    if (!selectedFile.name.toLowerCase().endsWith(".pdf")) {
      setError("Please select a PDF file.");
      return;
    }

    setFile(selectedFile);
    setError("");
    setUploadMessage("");
  };

  // =====================================================
  // DRAG AND DROP
  // =====================================================

  const handleDrop = (event) => {
    event.preventDefault();

    const droppedFile = event.dataTransfer.files[0];

    if (!droppedFile) {
      return;
    }

    if (!droppedFile.name.toLowerCase().endsWith(".pdf")) {
      setError("Please drop a PDF file.");
      return;
    }

    setFile(droppedFile);
    setError("");
    setUploadMessage("");
  };

  const handleDragOver = (event) => {
    event.preventDefault();
  };

  // =====================================================
  // UPLOAD PDF
  // =====================================================

  const handleUpload = async () => {
    if (!file) {
      setError("Please choose a PDF first.");
      return;
    }

    setUploading(true);
    setError("");
    setUploadMessage("");

    try {
      const formData = new FormData();

      formData.append("file", file);

      const response = await fetch(
        `${API_URL}/api/upload`,
        {
          method: "POST",
          body: formData,
        }
      );

      const data = await response.json();

      if (!response.ok) {
        throw new Error(
          data.detail || "PDF upload failed."
        );
      }

      setUploadMessage(
        `✓ ${data.filename} uploaded successfully. ${data.chunks} chunks indexed.`
      );

    } catch (err) {
      setError(err.message);
    } finally {
      setUploading(false);
    }
  };

  // =====================================================
  // ASK QUESTION
  // =====================================================

  const handleAsk = async () => {
    if (!question.trim()) {
      setError("Please enter a question.");
      return;
    }

    setAsking(true);
    setError("");
    setAnswer("");
    setSources([]);

    try {
      const response = await fetch(
        `${API_URL}/api/query`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            question: question,
            top_k: topK,
          }),
        }
      );

      const data = await response.json();

      if (!response.ok) {
        throw new Error(
          data.detail || "Question failed."
        );
      }

      setAnswer(
        data.answer || "No answer was returned."
      );

      setSources(
        data.sources || []
      );

    } catch (err) {
      setError(err.message);
    } finally {
      setAsking(false);
    }
  };

  // =====================================================
  // UI
  // =====================================================

  return (
    <div className="page">

      <main className="app-container">

        {/* =============================================
            UPLOAD SECTION
            ============================================= */}

        <section className="section">

          <h1>Upload a PDF to Ingest</h1>

          <label className="label">
            Choose a PDF
          </label>

          <div
            className="drop-zone"
            onDrop={handleDrop}
            onDragOver={handleDragOver}
            onClick={() =>
              document
                .getElementById("pdf-input")
                .click()
            }
          >

            <div className="upload-icon">
              ☁
            </div>

            <div className="drop-text">
              {file
                ? file.name
                : "Drag and drop file here"}
            </div>

            <div className="drop-subtext">
              Limit 200MB per file • PDF
            </div>

            <button
              type="button"
              className="browse-button"
              onClick={(event) => {
                event.stopPropagation();

                document
                  .getElementById("pdf-input")
                  .click();
              }}
            >
              Browse files
            </button>

          </div>

          <input
            id="pdf-input"
            type="file"
            accept=".pdf"
            onChange={handleFileChange}
            hidden
          />

          {file && (
            <div className="selected-file">
              Selected: <strong>{file.name}</strong>
            </div>
          )}

          <button
            className="upload-button"
            onClick={handleUpload}
            disabled={uploading}
          >
            {uploading
              ? "Uploading..."
              : "Upload PDF"}
          </button>

          {uploadMessage && (
            <div className="success-message">
              {uploadMessage}
            </div>
          )}

        </section>


        {/* DIVIDER */}

        <div className="divider"></div>


        {/* =============================================
            QUESTION SECTION
            ============================================= */}

        <section className="section">

          <h2>
            Ask a question about your PDFs
          </h2>

          <div className="question-box">

            <label className="field-label">
              Your question
            </label>

            <input
              type="text"
              className="question-input"
              placeholder="Ask a question..."
              value={question}
              onChange={(event) =>
                setQuestion(event.target.value)
              }
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  handleAsk();
                }
              }}
            />


            {/* TOP K */}

            <label className="field-label top-label">
              How many chunks to retrieve
            </label>

            <div className="number-control">

              <input
                type="number"
                min="1"
                max="10"
                value={topK}
                onChange={(event) => {
                  const value = Number(
                    event.target.value
                  );

                  if (value >= 1 && value <= 10) {
                    setTopK(value);
                  }
                }}
              />

              <button
                type="button"
                onClick={() =>
                  setTopK(
                    Math.max(1, topK - 1)
                  )
                }
              >
                −
              </button>

              <button
                type="button"
                onClick={() =>
                  setTopK(
                    Math.min(10, topK + 1)
                  )
                }
              >
                +
              </button>

            </div>


            {/* ASK BUTTON */}

            <button
              className="ask-button"
              onClick={handleAsk}
              disabled={asking}
            >
              {asking
                ? "Thinking..."
                : "Ask"}
            </button>

          </div>


          {/* ERROR */}

          {error && (
            <div className="error-message">
              {error}
            </div>
          )}


          {/* =========================================
              ANSWER
              ========================================= */}

          {answer && (
            <div className="result">

              <h3>Answer</h3>

              <p className="answer">
                {answer}
              </p>


              {/* SOURCES */}

              {sources.length > 0 && (
                <>
                  <h4>Sources</h4>

                  <ul className="sources">

                    {sources.map(
                      (source, index) => (
                        <li key={index}>
                          {source}
                        </li>
                      )
                    )}

                  </ul>
                </>
              )}

            </div>
          )}

        </section>

      </main>

    </div>
  );
}

export default App;