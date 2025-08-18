import './StackGraph.css';

function StackGraph({ stack }) {
  if (!stack || stack.length === 0) return null;
  return (
    <div className="stack-graph">
      {stack.map((frame, idx) => (
        <div className="stack-frame" key={idx}>
          <div className="stack-variable-container">
            {frame.variables.map((v, i) => (
              <div className="stack-variable" key={i}>
                {v.key} = {v.value}
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

export default StackGraph;
