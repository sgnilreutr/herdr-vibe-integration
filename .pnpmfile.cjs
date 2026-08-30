// pnpm hooks for strict safety rules
// https://pnpm.io/hooks

const { readFileSync } = require('fs');
const { resolve } = require('path');

/**
 * Check for non-pinned versions in package.json
 */
function hasNonPinnedVersion(version) {
  if (!version) return false;
  return version.includes('^') || version.includes('~') || version.includes('>') || version.includes('<');
}

module.exports = {
  hooks: {
    afterAllResolved: (lockfile) => {
      const errors = [];
      
      // Check root package.json
      const rootPkgPath = resolve(__dirname, 'package.json');
      const adapterPkgPath = resolve(__dirname, 'adapter', 'package.json');
      
      [rootPkgPath, adapterPkgPath].forEach(pkgPath => {
        try {
          const pkgJson = JSON.parse(readFileSync(pkgPath, 'utf-8'));
          const pkgName = pkgJson.name || 'unknown';
          
          // Check dependencies
          const allDeps = {
            ...pkgJson.dependencies || {},
            ...pkgJson.devDependencies || {},
            ...pkgJson.peerDependencies || {},
            ...pkgJson.optionalDependencies || {}
          };
          
          for (const [depName, depVersion] of Object.entries(allDeps)) {
            if (hasNonPinnedVersion(depVersion)) {
              errors.push(`Non-pinned version in ${pkgName}: ${depName}@${depVersion}`);
            }
          }
        } catch (err) {
          // Package.json not found, skip
        }
      });
      
      // Fail if there are errors
      if (errors.length > 0) {
        console.error(`\n[pnpm-safety] ${errors.length} safety violation(s) detected:`);
        for (const error of errors) {
          console.error(`  - ${error}`);
        }
        console.error(`\n[pnpm-safety] To fix: Pin all versions in package.json (remove ^, ~, >, <)`);
        process.exit(1);
      } else {
        console.log(`[pnpm-safety] All package.json versions are pinned`);
      }

      return lockfile;
    }
  }
};
