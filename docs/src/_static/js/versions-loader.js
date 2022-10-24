const dataRootUrl = document
  .getElementById("documentation_options")
  .getAttribute("data-url_root");

const findRoot = () => {
  const href = window.location.href;
  const components = href.split("/");
  const upDirCount =
    (dataRootUrl === "./" ? 1 : dataRootUrl.split("/").length) + 1;
  return components.slice(0, components.length - upDirCount).join("/");
};

const findPage = () => {
  const href = window.location.href;
  const components = href.split("/");
  const upDirCount = dataRootUrl === "./" ? 1 : dataRootUrl.split("/").length;
  return components.slice(components.length - upDirCount).join("/");
};

const root = findRoot();
const thisPage = findPage();

const makeVersionElement = (version) => {
  const versionURL = [root, version, thisPage].join("/");
  return `<dd><a href="${versionURL}">${version}</a></dd>`;
};

fetch(root + "/versions.txt")
  .then((response) => {
    return response.text();
  })
  .then((data) => data.split("\n").map(makeVersionElement).join("\n"))
  .then((data) => {
    const versionsList = document.querySelector("#versions-list");
    const html = versionsList.innerHTML;
    versionsList.innerHTML = html + "\n" + data;
  });
