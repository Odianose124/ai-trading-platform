import { useEffect, useState } from "react";

function App() {
  const [backendMessage, setBackendMessage] = useState("Connecting to backend...");
  const [error, setError] = useState("");

  useEffect(() => {
    fetch(`${import.meta.env.VITE_API_URL}/`)
      .then((response) => {
        if (!response.ok) {
          throw new Error("Backend request failed");
        }

        return response.json();
      })
      .then((data) => {
        setBackendMessage(data.message);
      })
      .catch(() => {
        setError("Unable to connect to the backend.");
      });
  }, []);

  return (
    <div>
      <h1>AI Trading Platform</h1>

      <p>Frontend: Online</p>

      {error ? (
        <p>{error}</p>
      ) : (
        <p>Backend: {backendMessage}</p>
      )}
    </div>
  );
}

export default App;