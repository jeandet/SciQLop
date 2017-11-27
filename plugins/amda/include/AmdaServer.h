#ifndef SCIQLOP_AMDASERVER_H
#define SCIQLOP_AMDASERVER_H

#include <QLoggingCategory>

#include <memory>

Q_DECLARE_LOGGING_CATEGORY(LOG_AmdaServer)

/**
 * @brief The AmdaServer class represents the server used to retrieve AMDA data (singleton).
 *
 * The server instance is initialized at compile time, as defined by the AMDA_SERVER value.
 */
class AmdaServer {
public:
    /// @return the unique instance of the AMDA server
    static AmdaServer &instance();

    virtual ~AmdaServer() noexcept = default;

    /// @return the name of the server
    virtual QString name() const = 0;
    /// @return the url of the server (used to retrieve data)
    virtual QString url() const = 0;
};

#endif // SCIQLOP_AMDASERVER_H
